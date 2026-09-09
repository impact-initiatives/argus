import re
from typing import Any

import polars as pl

"""
This is used to convert kobo skip logic into a polars expression.

Not all possible functions are currently supported. Any unsuported 
functions will raise an error.

Cross dataset column references are not supported and will raise
an error.
"""

# Tokenizer

TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<ref>\$\{[^}]+\})
    | (?P<string>'[^']*'|"[^"]*")
    | (?P<number>\d+\.\d+|\d+)
    | (?P<op>>=|<=|!=|=|>|<|\+|-|\*|\(|\)|,)
    | (?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)
    """,
    re.VERBOSE,
)

REF_RE = re.compile(r"\$\{([^}]+)\}")


def get_all_references(expressions: list[str]):
    """
    Extracts all referenced columns from a list of skip logic expressions
    """
    references = set().union(
        *({m.strip().lower() for m in REF_RE.findall(expression)} for expression in expressions)
    )
    return references


def tokenize(text: str) -> list[tuple[str, Any]]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Skip logic parser: Cannot tokenize near: {text[pos : pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        value = m.group()
        if kind == "ws":
            continue
        if kind == "ref":
            tokens.append(("REF", value[2:-1].strip().lower()))  # strip ${ }
        elif kind == "string":
            tokens.append(("STR", value[1:-1]))
        elif kind == "number":
            tokens.append(("NUM", value))
        elif kind == "op":
            tokens.append(("OP", value))
        else:
            tokens.append(("NAME", value))  # and/or/not/div/mod/selected...
    return tokens


# Recursive-descent parser  (produces tuple-based AST nodes)
# Precedence (loosest -> tightest):  or, and, not, comparison, +- , */div/mod

COMPARISON_OPS = {"=", "!=", "<", ">", "<=", ">="}


class Parser:
    def __init__(self, tokens: list[tuple[str, Any]]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> tuple[str, Any] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def advance(self) -> tuple[str, Any]:
        tok = self.peek()
        if tok is None:
            raise ValueError("Skip logic parser: Unexpected end of expression")
        self.i += 1
        return tok

    def expect_op(self, symbol: str) -> None:
        tok = self.advance()
        if tok != ("OP", symbol):
            raise ValueError(f"Skip logic parser: Expected {symbol!r}, got {tok}")

    def parse(self):
        node = self.parse_or()
        if self.peek() is not None:
            raise ValueError(f"Skip logic parser: Trailing tokens: {self.tokens[self.i :]}")
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.peek() == ("NAME", "or"):
            self.advance()
            node = ("or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.peek() == ("NAME", "and"):
            self.advance()
            node = ("and", node, self.parse_not())
        return node

    def parse_not(self):
        if self.peek() == ("NAME", "not"):
            self.advance()
            return ("not", self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self):
        node = self.parse_additive()
        tok = self.peek()
        if tok is not None and tok[0] == "OP" and tok[1] in COMPARISON_OPS:
            self.advance()
            return ("cmp", tok[1], node, self.parse_additive())
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.peek() in (("OP", "+"), ("OP", "-")):
            op = self.advance()[1]
            node = ("arith", op, node, self.parse_multiplicative())
        return node

    def parse_multiplicative(self):
        node = self.parse_atom()
        while True:
            tok = self.peek()
            if tok in (("OP", "*"),) or (
                tok is not None and tok[0] == "NAME" and tok[1] in ("div", "mod")
            ):
                op = self.advance()
                op_name = op[1] if op[0] == "NAME" else op[1]
                node = ("arith", op_name, node, self.parse_atom())
            else:
                return node

    def parse_atom(self):
        tok = self.advance()
        kind, value = tok

        if kind == "REF":
            return ("ref", value)
        if kind == "STR":
            return ("lit", value)
        if kind == "NUM":
            return ("num", value)
        if kind == "OP" and value == "(":
            node = self.parse_or()
            self.expect_op(")")
            return node
        if kind == "OP" and value == "-":
            node = self.parse_atom()
            if node[0] == "num":
                # -(-5) = 5: absorb instead of producing the unparsable '--5'
                if node[1].startswith("-"):
                    return ("num", node[1][1:])
                return ("num", "-" + node[1])
            return ("neg", node)
        if kind == "NAME":
            if self.peek() == ("OP", "("):  # function call
                self.advance()

                if self.peek() == ("OP", ")"):
                    # Zero-argument function: true(), false(), ...
                    self.advance()
                    if value in ("true", "false"):
                        return ("bool", value == "true")
                    raise ValueError(
                        f"Skip logic parser: Unsupported function: {value}()."
                        + " Raise an issue to have it added."
                    )

                # At least one argument
                args = [self.parse_or()]
                while self.peek() == ("OP", ","):
                    self.advance()
                    args.append(self.parse_or())
                self.expect_op(")")

                if value == "selected":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError("Skip logic parser: selected() expects (${var}, 'value')")
                    if args[1][0] != "lit":
                        raise ValueError(
                            "Skip logic parser: selected() value must be a quoted string"
                        )
                    return ("selected", args[0][1], args[1][1])

                if value == "starts-with":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError(
                            "Skip logic parser: starts-with() expects (${var}, 'prefix')"
                        )
                    if args[1][0] != "lit":
                        raise ValueError(
                            "Skip logic parser: starts-with() value must be a quoted string"
                        )
                    return ("starts_with", args[0][1], args[1][1])

                if value == "ends-with":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError(
                            "Skip logic parser: ends-with() expects (${var}, 'suffix')"
                        )
                    if args[1][0] != "lit":
                        raise ValueError(
                            "Skip logic parser: ends-with() value must be a quoted string"
                        )
                    return ("ends_with", args[0][1], args[1][1])

                if value == "contains":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError(
                            "Skip logic parser: contains() expects (${var}, 'substring')"
                        )
                    if args[1][0] != "lit":
                        raise ValueError(
                            "Skip logic parser: contains() value must be a quoted string"
                        )
                    return ("contains", args[0][1], args[1][1])

                if value == "regex":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError("Skip logic parser: regex() expects (${var}, 'pattern')")
                    if args[1][0] != "lit":
                        raise ValueError(
                            "Skip logic parser: regex() pattern must be a quoted string"
                        )
                    return ("regex", args[0][1], args[1][1])

                if value == "string-length":
                    if len(args) != 1 or args[0][0] != "ref":
                        raise ValueError("Skip logic parser: string-length() expects (${var},)")
                    return ("string_length", args[0][1])

                if value == "coalesce":
                    if len(args) != 2:
                        raise ValueError(
                            "Skip logic parser: coalesce() expects exactly 2 arguments"
                        )
                    return ("coalesce", args[0], args[1])

                if value == "concat":
                    if not args:
                        raise ValueError(
                            "Skip logic parser: concat() requires at least one argument"
                        )
                    return ("concat", args)

                if value == "if":
                    if len(args) != 3:
                        raise ValueError("Skip logic parser: if() expects (condition, then, else)")
                    return ("if", args[0], args[1], args[2])

                if value in ("int", "number"):
                    if len(args) != 1:
                        raise ValueError(f"Skip logic parser: {value}() takes exactly one argument")
                    return ("num_cast", value, args[0])

                if value == "count-selected":
                    if len(args) != 1 or args[0][0] != "ref":
                        raise ValueError("Skip logic parser: count-selected() expects (${var},)")
                    return ("count_selected", args[0][1])

                if value == "sum":
                    if not args:
                        raise ValueError("Skip logic parser: sum() requires at least one argument")
                    if any(arg[0] != "ref" for arg in args):
                        raise ValueError(
                            "Skip logic parser: sum() expects (${var}, ${var2}, ...)"
                            + " — all arguments must be column references"
                        )
                    return ("sum", [arg[1] for arg in args])

                if value in ("true", "false"):
                    raise ValueError(f"Skip logic parser: {value}() takes no arguments")

                raise ValueError(f"Skip logic parser: Unsupported function: {value}()")

            if value in ("true", "false"):
                return ("bool", value == "true")

        raise ValueError(f"Skip logic parser: Unexpected token: {tok}")


# AST -> Polars expression

CMP_MAP = {
    "=": lambda left_side, right_side: left_side == right_side,
    "!=": lambda left_side, right_side: left_side != right_side,
    "<": lambda left_side, right_side: left_side < right_side,
    ">": lambda left_side, right_side: left_side > right_side,
    "<=": lambda left_side, right_side: left_side <= right_side,
    ">=": lambda left_side, right_side: left_side >= right_side,
}

ARITH_MAP = {
    "+": lambda left_side, right_side: left_side + right_side,
    "-": lambda left_side, right_side: left_side - right_side,
    "*": lambda left_side, right_side: left_side * right_side,
    "div": lambda left_side, right_side: left_side / right_side,
    "mod": lambda left_side, right_side: left_side % right_side,
}


def _to_expr(node, schema: dict[str, pl.DataType]) -> pl.Expr:
    def _is_numeric_node(node) -> bool:
        """True if the node evaluates to a number by construction."""
        if node[0] in ("num", "arith", "count_selected", "sum"):
            return True
        if node[0] == "neg":
            return _is_numeric_node(node[1])

        return node[0] in ("string_length",)

    kind = node[0]

    if kind == "lit":
        return pl.lit(node[1])
    if kind == "num":
        return pl.lit(float(node[1]))
    if kind == "bool":
        return pl.lit(node[1])
    if kind == "ref":
        name = node[1]
        col = pl.col(name)
        if schema[name] in (pl.String, pl.Utf8):
            return col.str.strip_chars().replace("", None)
        return col

    if kind == "or":
        return _to_expr(node[1], schema) | _to_expr(node[2], schema)
    if kind == "and":
        return _to_expr(node[1], schema) & _to_expr(node[2], schema)
    if kind == "not":
        return ~_to_expr(node[1], schema)

    if kind == "neg":
        return -_to_expr(node[1], schema).cast(pl.Float64, strict=False)

    if kind == "cmp":
        _, op, left, right = node
        left_side, right_side = (
            _to_expr(left, schema),
            _to_expr(right, schema),
        )

        # Force numeric cast if either side contains arithmetic operations.
        # +, -, *, div, mod are only defined for numbers.
        if _is_numeric_node(left) or _is_numeric_node(right):
            # literal numbers or count-selected()
            # rounding for cases when 1 changes to 1.0
            left_side = left_side.cast(pl.Float64, strict=False).round(3)
            right_side = right_side.cast(pl.Float64, strict=False).round(3)

        elif node[1][0] == "lit" or node[3][0] == "lit":
            left_side = left_side.cast(pl.String, strict=False)
            right_side = right_side.cast(pl.String, strict=False)

        return CMP_MAP[op](left_side, right_side).fill_null(False)

    if kind == "arith":
        _, op, left, right = node
        left_side, right_side = (
            _to_expr(left, schema),
            _to_expr(right, schema),
        )
        left_side = left_side.cast(pl.Float64, strict=False)
        right_side = right_side.cast(pl.Float64, strict=False)
        return ARITH_MAP[op](left_side, right_side)

    if kind == "selected":
        _, var, value = node
        # Multi-select answers are stored as space-separated option codes,
        # e.g. "yes water food". This also works for select_one columns.

        return (
            pl.col(var)
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .str.split(" ")
            .list.contains(value.lower())
            .fill_null(False)
        )

    if kind == "starts_with":
        _, var, value = node
        # Prefix match on the first word of the (possibly space-separated)
        # answer. Lowercased for consistency with selected().
        return (
            pl.col(var)
            .cast(pl.String, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .str.starts_with(value.lower())
            .fill_null(False)
        )

    if kind == "ends_with":
        _, var, value = node
        return (
            pl.col(var)
            .cast(pl.String, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .str.ends_with(value.lower())
            .fill_null(False)
        )

    if kind == "contains":
        _, var, value = node
        # literal=True: the argument is a plain substring, never a regex,
        # so characters like '(' or '*' match literally (ODK behaviour).
        return (
            pl.col(var)
            .cast(pl.String, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .str.contains(pl.lit(value.lower()), literal=True)
            .fill_null(False)
        )

    if kind == "regex":
        _, var, pattern = node
        return (
            pl.col(var)
            .cast(pl.String, strict=False)
            .str.strip_chars()
            .str.contains(pattern)
            .fill_null(False)
        )

    if kind == "string_length":
        _, var = node
        # string-length of an unanswered question is 0 (ODK returns the
        # length of ''; a null-propagating len() would poison arithmetic)
        return (
            pl.when(pl.col(var).is_null())
            .then(pl.lit(0))
            .otherwise(pl.col(var).cast(pl.String, strict=False).str.strip_chars().str.len_chars())
            .cast(pl.Float64)
        )

    if kind == "coalesce":
        left_side = _to_expr(node[1], schema)
        right_side = _to_expr(node[2], schema)
        return pl.coalesce(left_side, right_side)

    if kind == "concat":
        parts = [_to_expr(a, schema).cast(pl.String, strict=False).fill_null("") for a in node[1]]
        out = parts[0]
        for part in parts[1:]:
            out = out + part
        return out

    if kind == "if":
        _, cond, then_node, else_node = node
        return (
            pl.when(_to_expr(cond, schema).fill_null(False))
            .then(_to_expr(then_node, schema))
            .otherwise(_to_expr(else_node, schema))
        )

    if kind == "num_cast":
        _, fn, arg = node
        dtype = pl.Int64 if fn == "int" else pl.Float64
        return _to_expr(arg, schema).cast(dtype, strict=False)

    if kind == "count_selected":
        _, var = node
        # Number of selected options. An unanswered (null/empty) question
        # must yield 0 — a raw split on null would give a null length
        # and poison the surrounding arithmetic.

        return (
            pl.when(pl.col(var).is_null())
            .then(pl.lit(0))
            .otherwise(
                pl.col(var)
                .cast(pl.String, strict=False)
                .str.strip_chars()
                .replace("", None)
                .str.split(" ")
                .list.len()
            )
            .fill_null(0)
        )

    if kind == "sum":
        _, vars_ = node
        # Row-wise sum across the referenced columns. Unanswered refs
        # contribute 0 (ODK: sum over an empty nodeset is 0), and a null
        # part must never poison the result with a null sum.
        parts = [
            (
                pl.when(pl.col(v).is_null())
                .then(pl.lit(0.0))
                .otherwise(
                    pl.col(v).cast(pl.String, strict=False).str.strip_chars().replace("", None)
                )
                .cast(pl.Float64, strict=False)
                .fill_null(0.0)
            )
            for v in vars_
        ]
        out = parts[0]
        for part in parts[1:]:
            out = out + part
        return out

    raise ValueError(f"Skip logic parser: Unknown node: {node}")


def _iter_refs(node):
    kind = node[0]
    if kind in (
        "ref",
        "selected",
        "count_selected",
        "starts_with",
        "ends_with",
        "contains",
        "regex",
        "string_length",
    ):
        yield node[1]
    elif kind == "sum":
        yield from node[1]
    elif kind in ("cmp", "arith"):
        yield from _iter_refs(node[2])
        yield from _iter_refs(node[3])
    elif kind in ("and", "or", "coalesce"):
        yield from _iter_refs(node[1])
        yield from _iter_refs(node[2])
    elif kind in ("not", "neg", "num_cast"):
        yield from _iter_refs(node[1])
    elif kind == "concat":
        for arg in node[1]:
            yield from _iter_refs(arg)
    elif kind == "if":
        yield from _iter_refs(node[1])
        yield from _iter_refs(node[2])
        yield from _iter_refs(node[3])


def build_relevance_expression(relevant: str, schema: dict[str, pl.DataType]) -> pl.Expr:
    """Parse a Kobo 'relevant' string into a single non-null Boolean Polars expr."""
    ast = Parser(tokenize(str(relevant))).parse()
    for ref in _iter_refs(ast):
        if ref not in schema:
            raise KeyError(
                f"Skip logic parser: Referenced column {ref!r} not found in data."
                + " Note: cross dataset references are currently not supported."
            )

    return _to_expr(ast, schema).fill_null(False)


# Validator: compare skip logic against the collected data


def is_missing(col: str) -> pl.Expr:
    # null, empty string, or whitespace-only
    return (
        pl.col(col)
        .cast(pl.String, strict=False)
        .str.strip_chars()
        .eq("")
        .fill_null(True)  # null -> True (missing)
    )
