import re
from typing import Any

import polars as pl

# ---------------------------------------------------------------------------
# 1. Tokenizer
# ---------------------------------------------------------------------------

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


def tokenize(text: str) -> list[tuple[str, Any]]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Cannot tokenize near: {text[pos : pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        value = m.group()
        if kind == "ws":
            continue
        if kind == "ref":
            tokens.append(("REF", value[2:-1].strip()))  # strip ${ }
        elif kind == "string":
            tokens.append(("STR", value[1:-1]))
        elif kind == "number":
            tokens.append(("NUM", value))
        elif kind == "op":
            tokens.append(("OP", value))
        else:
            tokens.append(("NAME", value))  # and/or/not/div/mod/selected...
    return tokens


# ---------------------------------------------------------------------------
# 2. Recursive-descent parser  (produces tuple-based AST nodes)
#
# Precedence (loosest -> tightest):  or, and, not, comparison, +- , */div/mod
# ---------------------------------------------------------------------------

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
            raise ValueError("Unexpected end of expression")
        self.i += 1
        return tok

    def expect_op(self, symbol: str) -> None:
        tok = self.advance()
        if tok != ("OP", symbol):
            raise ValueError(f"Expected {symbol!r}, got {tok}")

    def parse(self):
        node = self.parse_or()
        if self.peek() is not None:
            raise ValueError(f"Trailing tokens: {self.tokens[self.i :]}")
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
                return ("num", "-" + node[1])  # fold: -999 becomes a single numeric literal
            return ("neg", node)

        if kind == "NAME":
            if self.peek() == ("OP", "("):  # function call
                self.advance()
                args = [self.parse_or()]
                while self.peek() == ("OP", ","):
                    self.advance()
                    args.append(self.parse_or())
                self.expect_op(")")

                if value in ("true", "false"):      # function form: true() / false()
                    if args:                        # these take no arguments
                        raise ValueError(f"{value}() takes no arguments")
                    return ("bool", value == "true")

                if value == "selected":
                    if len(args) != 2 or args[0][0] != "ref":
                        raise ValueError("selected() expects (${var}, 'value')")
                    if args[1][0] != "lit":
                        raise ValueError("selected() value must be a quoted string")
                    return ("selected", args[0][1], args[1][1])

                if value == "count-selected":
                    if len(args) != 1 or args[0][0] != "ref":
                        raise ValueError("count-selected() expects (${var},)")
                    return ("count_selected", args[0][1])

                raise ValueError(f"Unsupported function: {value}()")

        raise ValueError(f"Unexpected token: {tok}")


# ---------------------------------------------------------------------------
# 3. AST -> Polars expression
# ---------------------------------------------------------------------------

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


def _to_expr(node, df_columns: set[str],  schema: dict[str, pl.DataType]) -> pl.Expr:
    def _is_numeric_node(node) -> bool:
        """True if the node evaluates to a number by construction."""
        if node[0] == "num":
            return True
        if node[0] == "neg":
            return _is_numeric_node(node[1])
        if node[0] == "arith":
            return True
        return node[0] == "count_selected"


    kind = node[0]

    if kind == "lit":
        return pl.lit(node[1])
    if kind == "num":
        return pl.lit(float(node[1]))
    if kind == "bool":
        return pl.lit(node[1])
    if kind == "ref":
        name = node[1]
        if name not in schema:
            raise KeyError(f"Referenced column {name!r} not found in data")
        col = pl.col(name)
        if schema[name] in (pl.String, pl.Utf8):
            return col.str.strip_chars().replace("", None)
        return col

    if kind == "or":
        return _to_expr(node[1], df_columns, schema) | _to_expr(node[2], df_columns, schema)
    if kind == "and":
        return _to_expr(node[1], df_columns, schema) & _to_expr(node[2], df_columns, schema)
    if kind == "not":
        return ~_to_expr(node[1], df_columns, schema)

    if kind == "neg":
        return -_to_expr(node[1], df_columns, schema)

    if kind == "cmp":
        _, op, left, right = node
        left_side, right_side = _to_expr(left, df_columns, schema), _to_expr(right, df_columns, schema)
        
        # Force numeric cast if either side contains arithmetic operations.
        # In ODK/XPath, +, -, *, div, mod are only defined for numbers.
        if _is_numeric_node(left) or _is_numeric_node(right):
            # Existing heuristic: literal numbers or count-selected()
            left_side = left_side.cast(pl.Float64, strict=False)
            right_side = right_side.cast(pl.Float64, strict=False)
        
        return CMP_MAP[op](left_side, right_side).fill_null(False)

    if kind == "arith":
        _, op, left, right = node
        left_side, right_side = _to_expr(left, df_columns, schema), _to_expr(right, df_columns, schema)
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

    if kind == "count_selected":
        _, var = node
        # Number of selected options. An unanswered (null/empty) question
        # must yield 0, matching ODK's behaviour — a raw split on null
        # would give a null length and poison the surrounding arithmetic.
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

    raise ValueError(f"Unknown node: {node}")


def build_relevance_expression(relevant: str, df_columns: set[str], schema: dict[str, pl.DataType]) -> pl.Expr:
    """Parse a Kobo 'relevant' string into a single non-null Boolean Polars expr."""
    ast = Parser(tokenize(str(relevant))).parse()
    return _to_expr(ast, df_columns, schema).fill_null(False)


# ---------------------------------------------------------------------------
# 4. Validator: compare skip logic against the collected data
# ---------------------------------------------------------------------------


def is_missing(col: str) -> pl.Expr:
    # null, empty string, or whitespace-only
    return (
        pl.col(col)
        .cast(pl.String, strict=False)
        .str.strip_chars()
        .eq("")
        .fill_null(True)  # null -> True (missing)
    )
