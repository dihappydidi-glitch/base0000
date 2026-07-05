#!/usr/bin/env python3
"""
Десятитысячно-единичная система счисления (base 10000).

Внутреннее представление — список разрядов (0..9999) в little-endian,
плюс знак. Все операции — поразрядно, без конвертации в машинный int.
Числа могут быть сколь угодно большими.

Формат строки:  left_half:right_half
  - ровно одно двоеточие
  - внутри половины группы разделяются точками
  - минус в начале — отрицательное число

Модель: цифры big-endian переплетаются между половинами.
BE = [L₀, R₀, L₁, R₁, ..., Lₙ₋₁, Rₙ₋₁]
Значение = Σ BE[i] × 10000^(2n-1-i)

Примеры:
    0000:0005                         →            5
    0001:0000                         →       10_000
    9999:9999                         →   99_999_999
    0000.0001:0000.0000               →       10_000
    0000.0000:0001.0000               →  100_000_000
    9999.9999:0000.0000               →  9_999_000_099_990_000
Обе половины всегда имеют одинаковое число групп.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


BASE = 10000


# ═══════════════════════════════════════════════════════════
#  ВНУТРЕННЕЕ ПРЕДСТАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════

@dataclass
class B10K:
    """
    Число в системе base-10000.

    sign:  1 или -1
    digs:  little-endian массив разрядов (0..9999)
           digs[0] + digs[1]*BASE + digs[2]*BASE^2 + ...
           Без ведущих нулей (кроме нуля: [0])
    """
    sign: int
    digs: List[int]

    # ── арифметические операторы ──────────────────────────

    def __neg__(self) -> 'B10K':
        return neg(self)

    def __pos__(self) -> 'B10K':
        return B10K(sign=self.sign, digs=list(self.digs))

    def __abs__(self) -> 'B10K':
        return B10K(sign=1, digs=list(self.digs))

    def __add__(self, other: 'B10K') -> 'B10K':
        return add(self, other)

    def __sub__(self, other: 'B10K') -> 'B10K':
        return sub(self, other)

    def __mul__(self, other: 'B10K') -> 'B10K':
        return mul(self, other)

    def __truediv__(self, other: 'B10K') -> 'B10K':
        return div(self, other)

    def __floordiv__(self, other: 'B10K') -> 'B10K':
        return div(self, other)

    def __mod__(self, other: 'B10K') -> 'B10K':
        return mod(self, other)

    def __divmod__(self, other: 'B10K') -> Tuple['B10K', 'B10K']:
        return div_mod(self, other)

    def __pow__(self, other: 'B10K') -> 'B10K':
        return pow_b10k(self, other)

    # ── сравнения ─────────────────────────────────────────

    def __eq__(self, other: 'B10K') -> bool:
        return self.sign == other.sign and _cmp_abs(self.digs, other.digs) == 0

    def __ne__(self, other: 'B10K') -> bool:
        return not (self == other)

    def __lt__(self, other: 'B10K') -> bool:
        if self.sign != other.sign:
            return self.sign < other.sign
        c = _cmp_abs(self.digs, other.digs)
        return (c < 0) if self.sign == 1 else (c > 0)

    def __le__(self, other: 'B10K') -> bool:
        return self < other or self == other

    def __gt__(self, other: 'B10K') -> bool:
        return not (self <= other)

    def __ge__(self, other: 'B10K') -> bool:
        return not (self < other)

    # ── строки ────────────────────────────────────────────

    def __str__(self) -> str:
        return format_num(self)

    def __repr__(self) -> str:
        return f"B10K({format_num(self)})"

    def __hash__(self):
        return hash((self.sign, tuple(self.digs)))

    def __bool__(self) -> bool:
        return not (len(self.digs) == 1 and self.digs[0] == 0)


# ═══════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════

def _zero() -> B10K:
    return B10K(sign=1, digs=[0])


def _trim(digs: List[int]) -> List[int]:
    """Убрать ведущие нули (в LE — хвостовые)."""
    while len(digs) > 1 and digs[-1] == 0:
        digs.pop()
    return digs


def _is_zero(a: B10K) -> bool:
    return len(a.digs) == 1 and a.digs[0] == 0


def _cmp_abs(a: List[int], b: List[int]) -> int:
    """Сравнить |a| и |b|. -1 / 0 / 1."""
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    for i in range(len(a) - 1, -1, -1):
        if a[i] != b[i]:
            return -1 if a[i] < b[i] else 1
    return 0


def _from_int(n: int) -> B10K:
    """Из обычного Python int (для тестов)."""
    if n == 0:
        return _zero()
    sign = 1 if n > 0 else -1
    n = abs(n)
    digs = []
    while n:
        digs.append(n % BASE)
        n //= BASE
    return B10K(sign=sign, digs=digs)


# ═══════════════════════════════════════════════════════════
#  ПОРАЗРЯДНЫЕ ОПЕРАЦИИ НАД |a|
# ═══════════════════════════════════════════════════════════

def _add_abs(a: List[int], b: List[int]) -> List[int]:
    """a + b, a,b >= 0, возвращает список цифр."""
    n = max(len(a), len(b))
    res = []
    carry = 0
    for i in range(n):
        da = a[i] if i < len(a) else 0
        db = b[i] if i < len(b) else 0
        s = da + db + carry
        res.append(s % BASE)
        carry = s // BASE
    if carry:
        res.append(carry)
    return _trim(res)


def _sub_abs(a: List[int], b: List[int]) -> List[int]:
    """a - b, a >= b >= 0."""
    res = []
    borrow = 0
    for i in range(len(a)):
        da = a[i]
        db = b[i] if i < len(b) else 0
        d = da - db - borrow
        if d < 0:
            d += BASE
            borrow = 1
        else:
            borrow = 0
        res.append(d)
    return _trim(res)


def _mul_abs(a: List[int], b: List[int]) -> List[int]:
    """a * b."""
    res = [0] * (len(a) + len(b))
    for i, da in enumerate(a):
        carry = 0
        for j, db in enumerate(b):
            prod = res[i + j] + da * db + carry
            res[i + j] = prod % BASE
            carry = prod // BASE
        if carry:
            res[i + len(b)] += carry
    return _trim(res)


def _mul_small(a: List[int], d: int) -> List[int]:
    """a * d, d = 0..9999."""
    if d == 0:
        return [0]
    res = []
    carry = 0
    for da in a:
        prod = da * d + carry
        res.append(prod % BASE)
        carry = prod // BASE
    if carry:
        res.append(carry)
    return _trim(res)


def _div_mod_abs(a: List[int], b: List[int]) -> Tuple[List[int], List[int]]:
    """a / b, a >= 0, b > 0. Возвращает (частное, остаток)."""
    cmp = _cmp_abs(a, b)
    if cmp < 0:
        return ([0], list(a))
    if cmp == 0:
        return ([1], [0])

    a_be = list(reversed(a))
    b_top = b[-1]

    quot = []
    rem_be = []

    for da in a_be:
        rem_be.append(da)

        if len(rem_be) >= len(b):
            r_hi = rem_be[0]
            if len(rem_be) > 1:
                r_hi = r_hi * BASE + rem_be[1]
            guess = r_hi // b_top
            if guess > 9999:
                guess = 9999
        else:
            quot.append(0)
            continue

        rem_le = _trim(list(reversed(rem_be)))

        while guess >= 0:
            prod = _mul_small(b, guess)
            if _cmp_abs(rem_le, prod) >= 0:
                break
            guess -= 1

        rem_le = _sub_abs(rem_le, prod)
        quot.append(guess)
        rem_be = list(reversed(rem_le)) if rem_le != [0] else []

    quot = _trim(list(reversed(quot)))
    rem = _trim(list(reversed(rem_be))) if rem_be else [0]
    return (quot, rem)


def _shift_left_abs(a: List[int], k: int) -> List[int]:
    """Умножить на BASE^k (сдвиг влево на k разрядов)."""
    if len(a) == 1 and a[0] == 0:
        return [0]
    return [0] * k + a  # LE: младшие разряды спереди


def _shift_right_abs(a: List[int], k: int) -> List[int]:
    """Целочисленно поделить на BASE^k (сдвиг вправо на k разрядов)."""
    if k >= len(a):
        return [0]
    return a[k:]  # LE: просто отбрасываем k младших разрядов


# ═══════════════════════════════════════════════════════════
#  ОСНОВНЫЕ ОПЕРАЦИИ
# ═══════════════════════════════════════════════════════════

def neg(a: B10K) -> B10K:
    if _is_zero(a):
        return _zero()
    return B10K(sign=-a.sign, digs=list(a.digs))


def add(a: B10K, b: B10K) -> B10K:
    if a.sign == b.sign:
        return B10K(sign=a.sign, digs=_add_abs(a.digs, b.digs))
    cmp = _cmp_abs(a.digs, b.digs)
    if cmp == 0:
        return _zero()
    if cmp > 0:
        return B10K(sign=a.sign, digs=_sub_abs(a.digs, b.digs))
    else:
        return B10K(sign=b.sign, digs=_sub_abs(b.digs, a.digs))


def sub(a: B10K, b: B10K) -> B10K:
    return add(a, neg(b))


def mul(a: B10K, b: B10K) -> B10K:
    if _is_zero(a) or _is_zero(b):
        return _zero()
    sign = 1 if a.sign == b.sign else -1
    return B10K(sign=sign, digs=_mul_abs(a.digs, b.digs))


def div_mod(a: B10K, b: B10K) -> Tuple[B10K, B10K]:
    """
    Целочисленное деление с остатком (Euclidean division).
    Всегда: a = q * b + r, где 0 <= r < |b|.
    """
    if _is_zero(b):
        raise ZeroDivisionError("деление на ноль")
    if _is_zero(a):
        return (_zero(), _zero())

    q_digs, r_digs = _div_mod_abs(a.digs, b.digs)

    # усечённое деление (truncate toward zero)
    q = B10K(sign=1 if a.sign == b.sign else -1, digs=q_digs)
    r = B10K(sign=a.sign, digs=_trim(r_digs))  # остаток = знак делимого

    # Евклидова коррекция: 0 <= r < |b|
    if r.sign == -1 and not _is_zero(r):
        # q = q - sign(b),  r = r + |b|
        q = sub(q, _from_int(1)) if b.sign == 1 else add(q, _from_int(1))
        r = add(r, abs(b))

    return (q, r)


def div(a: B10K, b: B10K) -> B10K:
    return div_mod(a, b)[0]


def mod(a: B10K, b: B10K) -> B10K:
    return div_mod(a, b)[1]


# ═══════════════════════════════════════════════════════════
#  ДОПОЛНИТЕЛЬНЫЕ ОПЕРАЦИИ
# ═══════════════════════════════════════════════════════════

def pow_b10k(a: B10K, b: B10K) -> B10K:
    """a ** b, b >= 0 (бинарное возведение в степень)."""
    if b.sign == -1:
        raise ValueError("отрицательная степень не поддерживается")
    if _is_zero(b):
        return _from_int(1)
    if _is_zero(a):
        return _zero()

    # Бинарное возведение в степень
    result = _from_int(1)
    base = a
    exp = b

    while not _is_zero(exp):
        if exp.digs[0] & 1:  # нечётное
            result = mul(result, base)
        base = mul(base, base)
        exp = div(exp, _from_int(2))

    return result


def fact(n: B10K) -> B10K:
    """n! (факториал)."""
    if n.sign == -1:
        raise ValueError("факториал отрицательного")
    if _is_zero(n) or (len(n.digs) == 1 and n.digs[0] == 1):
        return _from_int(1)
    result = _from_int(1)
    i = _from_int(2)
    one = _from_int(1)
    while i <= n:
        result = mul(result, i)
        i = add(i, one)
    return result


def gcd(a: B10K, b: B10K) -> B10K:
    """НОД (алгоритм Евклида)."""
    a = abs(a)
    b = abs(b)
    while not _is_zero(b):
        a, b = b, mod(a, b)
    return a


def lcm(a: B10K, b: B10K) -> B10K:
    """НОК."""
    return div(mul(a, b), gcd(a, b))


def shift_left(a: B10K, k: int) -> B10K:
    """a * BASE^k (сдвиг разрядов влево)."""
    if _is_zero(a) or k == 0:
        return B10K(sign=a.sign, digs=list(a.digs))
    return B10K(sign=a.sign, digs=_shift_left_abs(a.digs, k))


def shift_right(a: B10K, k: int) -> B10K:
    """a // BASE^k (сдвиг разрядов вправо)."""
    if k == 0:
        return B10K(sign=a.sign, digs=list(a.digs))
    return B10K(sign=a.sign, digs=_shift_right_abs(a.digs, k))


def isqrt(a: B10K) -> B10K:
    """
    Целочисленный квадратный корень (метод Ньютона — вавилонский).
    """
    if a.sign == -1:
        raise ValueError("квадратный корень из отрицательного")
    if _is_zero(a):
        return _zero()

    # начальное приближение: 2 ** (число_бит // 2)
    one = _from_int(1)
    x = _from_int(2)
    # поднимаем x² пока не превысит a
    while mul(x, x) <= a:
        x = mul(x, _from_int(2))

    # Ньютон
    while True:
        next_x = div(add(x, div(a, x)), _from_int(2))
        if next_x >= x:
            break
        x = next_x

    # Коррекция: x² может быть > a
    while mul(x, x) > a:
        x = sub(x, one)
    while mul(add(x, one), add(x, one)) <= a:
        x = add(x, one)

    return x


# ═══════════════════════════════════════════════════════════
#  ПАРСИНГ И ФОРМАТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════

def parse(s: str) -> B10K:
    """
    Строка → B10K (переплетающаяся модель).

    BE = [L₀, R₀, L₁, R₁, ..., Lₙ₋₁, Rₙ₋₁]
    """
    s = s.strip()
    while s and not (s[0].isdigit() or s[0] in '-.:'):
        s = s[1:]
    if not s:
        raise ValueError("пустая строка")
    sign = -1 if s.startswith('-') else 1
    if s.startswith('-'):
        s = s[1:]
    if not s:
        raise ValueError("пустая строка")

    split_pos = s.find(':')
    if split_pos < 0:
        left_part = ""
        right_part = s
    else:
        left_part = s[:split_pos]
        right_part = s[split_pos + 1:]

    left_groups = [int(g) for g in left_part.split('.') if g.strip() != ""]
    right_groups = [int(g) for g in right_part.split('.') if g.strip() != ""]

    for v in left_groups + right_groups:
        if not (0 <= v <= 9999):
            raise ValueError(f"цифра вне диапазона 0..9999: {v}")

    # Переплетение: [L₀, R₀, L₁, R₁, ...] в big-endian
    be = []
    n = max(len(left_groups), len(right_groups))
    for i in range(n):
        if i < len(left_groups):
            be.append(left_groups[i])
        if i < len(right_groups):
            be.append(right_groups[i])

    # BE → LE
    le = list(reversed(be))
    le = _trim(le)
    if not le:
        le = [0]

    return B10K(sign=sign, digs=le)


def format_num(a: B10K) -> str:
    """
    B10K → строка (переплетающаяся модель).

    Разбивает big-endian цифры на пары (Lᵢ, Rᵢ).
    """
    if _is_zero(a):
        return "0000:0000"

    # Little-endian → Big-endian
    be = list(reversed(a.digs))

    # Дополняем до чётного числа групп
    if len(be) % 2 != 0:
        be.insert(0, 0)

    # Чётные индексы → левая половина, нечётные → правая
    left = [be[i] for i in range(0, len(be), 2)]
    right = [be[i + 1] for i in range(0, len(be), 2)]

    left_strs = [f"{g:04d}" for g in left]
    right_strs = [f"{g:04d}" for g in right]

    s = ".".join(left_strs) + ":" + ".".join(right_strs)
    return f"-{s}" if a.sign == -1 else s


# ─── короткие псевдонимы ──────────────────────────────────

def B(s: str) -> B10K:
    """parse('0005') → B10K."""
    return parse(s)


def _(a: B10K) -> str:
    """format_num."""
    return format_num(a)


# ═══════════════════════════════════════════════════════════
#  REPL-КАЛЬКУЛЯТОР
# ═══════════════════════════════════════════════════════════

def _repl():
    """Интерактивный калькулятор."""
    try:
        import readline  # история, стрелки влево/вправо (UNIX)
    except ImportError:
        pass  # Windows — без readline, но работает
    print("=== base-10000 REPL ===")
    print("Вводите выражения вида:  0000:0005 + 0000:0003")
    print("Поддерживается: + - * / % ** //")
    print("Функции: fact(n)  gcd(a,b)  lcm(a,b)  isqrt(n)")
    print("Переменные: обозначаются буквами, сохраняются через =")
    print("  x = 0000:0100")
    print("  x * x")
    print("Выход: Ctrl+C или .exit")
    print()

    import operator as op_mod
    _ops = {
        '+': op_mod.add,
        '-': op_mod.sub,
        '*': op_mod.mul,
        '//': op_mod.floordiv,
        '/': op_mod.floordiv,
        '%': op_mod.mod,
        '**': op_mod.pow,
    }

    vars_dict = {}

    def eval_expr(tokens):
        """Simple expression evaluator: function(args), a op b, variable, or literal."""
        if not tokens:
            return None

        # Присваивание: name = expr
        if len(tokens) >= 3 and tokens[1] == '=':
            name = tokens[0]
            if not name.isidentifier():
                print(f"  неверное имя: {name}")
                return None
            val = eval_expr(tokens[2:])
            if val is not None:
                vars_dict[name] = val
                print(f"  {name} = {format_num(val)}")
            return None

        # Функции: func_name ( args )
        if (len(tokens) >= 3 and tokens[0].isidentifier()
                and tokens[1] == '(' and ')' in tokens):
            close_idx = tokens.index(')')
            func_name = tokens[0]
            raw_args = tokens[2:close_idx]
            # отделяем аргументы (через запятую или пробел)
            arg_str = ' '.join(raw_args).replace(',', ' ').replace('  ', ' ')
            arg_tokens = [t for t in arg_str.split() if t]
            args = []
            for t in arg_tokens:
                if t in vars_dict:
                    args.append(vars_dict[t])
                else:
                    try:
                        args.append(parse(t))
                    except Exception:
                        print(f"  не удалось разобрать: {t}")
                        return None
            # остаток выражения после )
            rest = eval_expr(tokens[close_idx + 1:])

            if func_name == 'fact':
                result = fact(args[0])
            elif func_name == 'gcd':
                result = gcd(args[0], args[1])
            elif func_name == 'lcm':
                result = lcm(args[0], args[1])
            elif func_name == 'isqrt':
                result = isqrt(args[0])
            else:
                print(f"  неизвестная функция: {func_name}")
                return None

            if rest is not None:
                # было что-то после функции: подразумеваем умножение
                return mul(result, rest)
            return result

        # Бинарная операция: a op b
        if len(tokens) >= 3:
            op_str = tokens[1]
            if op_str in _ops:
                # левый операнд
                if tokens[0] in vars_dict:
                    a = vars_dict[tokens[0]]
                else:
                    a = parse(tokens[0])
                # правый операнд (может быть функцией)
                rest = tokens[2:]
                if (len(rest) >= 2 and rest[0].isidentifier()
                        and rest[1] == '('):
                    b = eval_expr(rest)
                elif rest[0] in vars_dict:
                    b = vars_dict[rest[0]]
                else:
                    b = parse(rest[0])
                if b is None:
                    return None
                return _ops[op_str](a, b)

        # Унарное: одно значение (или переменная, или литерал)
        if tokens[0] in vars_dict:
            return vars_dict[tokens[0]]
        try:
            return parse(tokens[0])
        except Exception:
            print(f"  не удалось разобрать: {tokens[0]}")
            return None

    try:
        while True:
            try:
                line = input("b10k> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line in ('.exit', '.quit', 'exit', 'quit'):
                break

            try:
                # чистим BOM и непечатные символы (PowerShell)
                while line and not (line[0].isdigit() or line[0] in '-.:' or line[0].isalpha()):
                    line = line[1:]
                line = line.strip()
                # разбиваем на токены, сохраняя скобки
                tokens = line.replace('(', ' ( ').replace(')', ' ) ').replace('=', ' = ')
                tokens = tokens.replace(',', ' , ')
                tokens = [t for t in tokens.split() if t]

                result = eval_expr(tokens)
                if result is not None:
                    print(f"  {format_num(result)}")
            except Exception as e:
                print(f"  ошибка: {e}")

    except KeyboardInterrupt:
        print()
    print("Пока!")


# ═══════════════════════════════════════════════════════════
#  ТЕСТЫ
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if '--repl' in sys.argv:
        _repl()
        sys.exit(0)

    def test(name, a_str, b_str, op, expected):
        a = parse(a_str)
        b = parse(b_str)
        if op == '+':
            r = add(a, b)
        elif op == '-':
            r = sub(a, b)
        elif op == '*':
            r = mul(a, b)
        elif op == '/':
            r = div(a, b)
        elif op == '%':
            r = mod(a, b)
        elif op == '**':
            r = pow_b10k(a, b)
        got = format_num(r)
        ok = "OK" if got == expected else f"FAIL (expected {expected})"
        print(f"  {a_str} {op} {b_str} = {got:>30s}  {ok}")

    print("=== Сложение / вычитание ===")
    test("1",   "0000:0005", "0000:0003", '+', "0000:0008")
    test("2",   "0000:9999", "0000:0001", '+', "0001:0000")
    test("3",   "9999:9999", "0000:0001", '+', "0000.0000:0001.0000")
    test("4",   "0000:0005", "0000:0003", '-', "0000:0002")
    test("5",   "0001:0000", "0000:0001", '-', "0000:9999")
    test("6",   "0000:0005", "-0000:0003", '+', "0000:0002")
    test("7",   "0000:0003", "-0000:0005", '+', "-0000:0002")
    test("8",   "0000:0000", "0000:0000", '+', "0000:0000")

    print("\n=== Умножение ===")
    test("9",   "0000:0005", "0000:0003", '*', "0000:0015")
    test("10",  "0000:0012", "0000:0012", '*', "0000:0144")
    test("11",  "0000:9999", "0000:9999", '*', "9998:0001")
    test("12",  "9999:9999", "9999:9999", '*', "9999.0000:9998.0001")
    test("13",  "0001:0000", "0001:0000", '*', "0000.0000:0001.0000")
    test("14",  "-0000:0003", "0000:0005", '*', "-0000:0015")

    print("\n=== Деление и остаток ===")
    test("15",  "9998:0001", "0000:9999", '/', "0000:9999")
    test("16",  "0000.0000:0001.0000", "0001:0000", '/', "0001:0000")
    test("17",  "0001:0000", "0000:0003", '/', "0000:3333")
    test("18",  "0000:0015", "0000:0003", '/', "0000:0005")
    test("19",  "0000:0010", "0000:0003", '/', "0000:0003")
    test("20",  "0000:0010", "0000:0003", '%', "0000:0001")  # 10 % 3 = 1

    # отрицательные по евклиду
    q, r = div_mod(parse("-0000:0007"), parse("0000:0003"))
    print(f"  -0000:0007 // 0000:0003 = {format_num(q)}  r = {format_num(r)}  ", end="")
    print("OK" if format_num(q) == "-0000:0003" and format_num(r) == "0000:0002" else "FAIL")

    print("\n=== Степень ===")
    test("21",  "0000:0002", "0000:0010", '**', "0000:1024")   # 2^10 = 1024
    test("22",  "0000:0010", "0000:0000", '**', "0000:0001")   # 10^0 = 1

    print("\n=== Факториал ===")
    print(f"  fact(5)  = {_(fact(B('0000:0005')))}  (ожидается 0000:0120)")
    print(f"  fact(10) = {_(fact(B('0000:0010')))}")

    print("\n=== НОД / НОК ===")
    print(f"  gcd(12,8)  = {_(gcd(B('0000:0012'), B('0000:0008')))}  (ожидается 0000:0004)")
    print(f"  lcm(12,8)  = {_(lcm(B('0000:0012'), B('0000:0008')))}  (ожидается 0000:0024)")

    print("\n=== Квадратный корень ===")
    print(f"  isqrt(144) = {_(isqrt(B('0000:0144')))}  (ожидается 0000:0012)")
    print(f"  isqrt(2)   = {_(isqrt(B('0000:0002')))}  (ожидается 0000:0001)")

    print("\n=== Сдвиги ===")
    val = B("0000:0005")
    print(f"  shift_left(5, 2)  = {_(shift_left(val, 2))}  (5*10000^2)")
    print(f"  shift_right(5,1)  = {_(shift_right(val, 1))}  (5//10000=0)")

    val2 = B("0000.0000:0001.0000")  # 100,000,000
    print(f"  shift_right(1e8,2)= {_(shift_right(val2, 2))}  (100000000//10000^2=1)")

    print("\n=== Операторы Python ===")
    a, b = B("0000:0005"), B("0000:0003")
    print(f"  a+b = {_(a + b)}")
    print(f"  a-b = {_(a - b)}")
    print(f"  a*b = {_(a * b)}")
    print(f"  a//b = {_(a // b)}")
    print(f"  a%b = {_(a % b)}")
    print(f"  a**b = {_(a ** b)}  (5^3=125)")
    print(f"  -a = {_(-a)}")
    print(f"  abs(-a) = {_(abs(-a))}")
    print(f"  a == b: {a == b}")
    print(f"  a != b: {a != b}")
    print(f"  a < b:  {a < b}")
    print(f"  a > b:  {a > b}")

    print("\n=== REPL ===")
    print("  Запустите:  python3 base10000.py --repl")
