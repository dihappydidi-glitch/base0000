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
  - обе половины всегда имеют одинаковое количество групп;
    более короткая дополняется нулями справа (LSB-конец)

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
KARATSUBA_CUTOFF = 64  # цифр в base-10000 (~256 десятичных); порог переключения на Karatsuba


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
    frac_pairs: число дробных пар (0 = целое число).
                Устанавливается при создании дробного B10K (pi_b10k и т.п.)
                для корректной конвертации в десятичную строку с точкой.
    """
    sign: int
    digs: List[int]
    frac_pairs: int = 0

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
    return all(d == 0 for d in a.digs)


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


def _mul_abs_schoolbook(a: List[int], b: List[int]) -> List[int]:
    """a * b — школьное O(n²)."""
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


def _mul_abs_karatsuba(a: List[int], b: List[int]) -> List[int]:
    """Умножение Карацубы O(n^1.585) для LE-массивов цифр.

    Рекурсивно делит числа пополам:
        a = a_hi * BASE^k + a_lo
        b = b_hi * BASE^k + b_lo

        z0 = a_lo * b_lo
        z1 = a_hi * b_hi
        z2 = (a_lo + a_hi) * (b_lo + b_hi) - z0 - z1

        result = z1 * BASE^{2k} + z2 * BASE^k + z0
    """
    n = max(len(a), len(b))

    if n <= KARATSUBA_CUTOFF:
        return _mul_abs_schoolbook(a, b)

    # Выравнивание длины до n
    a = a + [0] * (n - len(a))
    b = b + [0] * (n - len(b))

    k = n // 2

    # Разделение: lo — младшие k цифр (первые в LE)
    a_lo = a[:k]
    a_hi = a[k:]
    b_lo = b[:k]
    b_hi = b[k:]

    # 3 рекурсивных умножения
    z0 = _mul_abs_karatsuba(a_lo, b_lo)
    z1 = _mul_abs_karatsuba(a_hi, b_hi)

    # (a_lo + a_hi) * (b_lo + b_hi)
    s_a = _add_abs(a_lo, a_hi)
    s_b = _add_abs(b_lo, b_hi)
    z2 = _mul_abs_karatsuba(_trim(s_a), _trim(s_b))

    # z2 = z2 - z0 - z1
    z2 = _sub_abs(z2, z0)
    z2 = _sub_abs(z2, z1)

    # Комбинирование: z1 * BASE^{2k} + z2 * BASE^k + z0
    result = _add_abs(z0, _shift_left_abs(z2, k))
    result = _add_abs(result, _shift_left_abs(z1, 2 * k))

    return _trim(result)


def _mul_abs(a: List[int], b: List[int]) -> List[int]:
    """a * b — автоматический выбор алгоритма."""
    if len(a) < KARATSUBA_CUTOFF or len(b) < KARATSUBA_CUTOFF:
        return _mul_abs_schoolbook(a, b)
    return _mul_abs_karatsuba(a, b)


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


def _div_small_abs(a: List[int], d: int) -> List[int]:
    """a // d (целочисленно), a >= 0, 0 < d < BASE.

    Эффективнее общего _div_mod_abs — O(n) вместо O(n²).
    """
    if d == 0:
        raise ZeroDivisionError("division by zero")
    if d == 1:
        return list(a)
    res_be = []
    rem = 0
    for da in reversed(a):  # от старших LE-разрядов (BE порядок)
        cur = rem * BASE + da
        res_be.append(cur // d)
        rem = cur % d
    # BE → LE
    le = list(reversed(res_be))
    return _trim(le)


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
    return B10K(sign=-a.sign, digs=list(a.digs), frac_pairs=a.frac_pairs)


def add(a: B10K, b: B10K) -> B10K:
    if a.sign == b.sign:
        result = B10K(sign=a.sign, digs=_add_abs(a.digs, b.digs))
    else:
        cmp = _cmp_abs(a.digs, b.digs)
        if cmp == 0:
            result = _zero()
        elif cmp > 0:
            result = B10K(sign=a.sign, digs=_sub_abs(a.digs, b.digs))
        else:
            result = B10K(sign=b.sign, digs=_sub_abs(b.digs, a.digs))
    result.frac_pairs = max(a.frac_pairs, b.frac_pairs)
    return result


def sub(a: B10K, b: B10K) -> B10K:
    return add(a, neg(b))


def mul(a: B10K, b: B10K) -> B10K:
    if _is_zero(a) or _is_zero(b):
        return _zero()
    sign = 1 if a.sign == b.sign else -1
    result = B10K(sign=sign, digs=_mul_abs(a.digs, b.digs))
    result.frac_pairs = a.frac_pairs + b.frac_pairs
    return result


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

    # Сохраняем дробность: если b — целое, результат сохраняет a.frac_pairs
    if b.frac_pairs == 0:
        q.frac_pairs = a.frac_pairs
        r.frac_pairs = a.frac_pairs

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


def _range_product(lo: int, hi: int) -> B10K:
    """Произведение int-чисел lo..hi как B10K через дерево (product tree).

    Разбивает диапазон пополам рекурсивно, чтобы малые множители
    перемножались первыми — это заменяет O(n²·log n) последовательного
    цикла на O(n^1.585 · log n) Karatsuba-дерева.
    """
    if lo > hi:
        return _from_int(1)
    if lo == hi:
        return _from_int(lo)
    # Малый диапазон — последовательно
    if hi - lo <= 32:
        r = _from_int(1)
        for i in range(lo, hi + 1):
            r = mul(r, _from_int(i))
        return r
    mid = (lo + hi) // 2
    left = _range_product(lo, mid)
    right = _range_product(mid + 1, hi)
    return mul(left, right)


def fact(n: B10K, *extra: B10K) -> B10K:
    """n! (факториал).

    Один аргумент: обычный факториал n! — использует product tree
    (разделяй-и-властвуй) для ускорения.
    Два аргумента: дробный B10K, где целая часть = fact(n),
    дробные группы = факториалы extra аргументов, разбитые на B10K-группы.
    Пример: fact(4, 769) → целая часть 24, дробная = fact(769) в base-10000
    """
    if n.sign == -1:
        raise ValueError("факториал отрицательного")
    if _is_zero(n) or (len(n.digs) == 1 and n.digs[0] == 1):
        int_result = _from_int(1)
    else:
        n_int = to_int(n)
        int_result = _range_product(1, n_int) if n_int >= 2 else _from_int(1)

    if not extra:
        return int_result

    # Дробная часть: факториал каждого extra → B10K LE-группы
    all_frac_groups: List[int] = []
    for f in extra:
        f_fact = fact(f)  # рекурсия (1 аргумент)
        all_frac_groups.extend(f_fact.digs)

    # Дополняем до чётного числа LE-групп (2 группы = 1 пара)
    if len(all_frac_groups) % 2 != 0:
        all_frac_groups.append(0)

    frac_pairs = len(all_frac_groups) // 2

    # LE: [frac_groups..., int_groups...]
    combined_digs = all_frac_groups + int_result.digs
    return B10K(sign=1, digs=combined_digs, frac_pairs=frac_pairs)


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


def sqrt_b10k(a: B10K, pairs: int = 0) -> B10K:
    """
    Квадратный корень с точностью до pairs дробных пар.

    pairs=0 → целочисленный sqrt (через isqrt).
    pairs>0 → сдвиг A на 4·pairs LE-групп влево, isqrt, отрезание
              дробной части.

    Пример: sqrt_b10k(parse('2'), 4) → sqrt(2) с 4 дробными парами.
    """
    if a.sign < 0:
        raise ValueError("sqrt из отрицательного числа")
    if _is_zero(a):
        if pairs:
            return B10K(sign=1, digs=[0], frac_pairs=pairs)
        return _zero()
    if pairs == 0:
        return isqrt(a)

    # Сдвигаем A на 4·pairs LE-групп для получения точности pairs пар.
    # isqrt(A·BASE^(4p)) ≈ sqrt(A)·BASE^(2p) — достаточно для 2p
    # LE-групп дробной части (= p пар).
    shifted = B10K(sign=1, digs=[0] * (4 * pairs) + a.digs)

    sqrt_int = isqrt(shifted)

    # Первые 2·pairs LE-групп — дробная часть (младшие разряды)
    frac_digs = sqrt_int.digs[:2 * pairs]
    int_digs = sqrt_int.digs[2 * pairs:]

    # Дополняем, если не хватило
    if len(frac_digs) < 2 * pairs:
        pad = [0] * (2 * pairs - len(frac_digs))
        frac_digs = pad + frac_digs

    # B10K: [дробь LE... | целая LE...], младшие → дробь
    return B10K(sign=1, digs=frac_digs + int_digs, frac_pairs=pairs)


# ═══════════════════════════════════════════════════════════
#  ПАРСИНГ И ФОРМАТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════

def parse(s: str) -> B10K:
    """
    Строка → B10K (переплетающаяся модель).
    Для целых чисел:  left_half:right_half
    Для дробных:      целая,левая_дробь:правая_дробь  (запятая = десятичный разделитель)

    BE = [L₀, R₀, L₁, R₁, ..., Lₙ₋₁, Rₙ₋₁]
    """
    s = s.strip()
    while s and not (s[0].isdigit() or s[0] in '-.,:'):
        s = s[1:]
    if not s:
        raise ValueError("пустая строка")
    sign = -1 if s.startswith('-') else 1
    if s.startswith('-'):
        s = s[1:]
        s = s.strip()
    if not s:
        raise ValueError("пустая строка после знака")

    if ',' in s:
        return _parse_frac(s, sign)
    return _parse_int(s, sign)


def _parse_int(s: str, sign: int) -> B10K:
    """Парсинг целого B10K (без запятой).

    Группы отображаются MSB→LSB (старшие разряды первыми).
    """
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

    # L не длиннее R (L ≤ R). Дополняем более короткую половину
    # нулями спереди (MSB-конец) для выравнивания.
    n = max(len(left_groups), len(right_groups))
    left_groups = [0] * (n - len(left_groups)) + left_groups
    right_groups = [0] * (n - len(right_groups)) + right_groups

    # LE = [Rₙ₋₁, Lₙ₋₁, ..., R₀, L₀] — LSB→MSB для хранения
    le = []
    for i in range(n - 1, -1, -1):
        le.append(right_groups[i])
        le.append(left_groups[i])
    le = _trim(le)
    if not le:
        le = [0]

    return B10K(sign=sign, digs=le)


def _parse_frac(s: str, sign: int) -> B10K:
    """
    Парсинг дробного B10K.

    Новый формат: int_part, L0.R0.L1.R1.L2.R2...
      — целая часть десятичным числом, дробная — чередование
        левых и правых 4-циферных групп
      Пример: "3,1415.9265.3589.7932"

    Старый формат (с ':') — для обратной совместимости:
      целая,дробь_левая:дробь_правая
      или
      дробь_левая:целая,дробь_правая

    Возвращает B10K, где дробные разряды объединены с целой частью
    как единое LE-число. Для форматирования требуется отдельно хранить
    число дробных пар — см. format_frac().
    """
    # Если есть ':' — старый формат
    if ':' in s:
        colon_pos = s.find(':')
        comma_pos = s.index(',')

        left_str = s[:colon_pos]
        right_str = s[colon_pos + 1:]

        comma_in_left = comma_pos < colon_pos

        if comma_in_left:
            # Старый формат: целая,дробь_левая:дробь_правая
            int_part_str, left_frac_str = left_str.split(',', 1)
            right_frac_str = right_str
            int_val = int(int_part_str) if int_part_str.strip() else 0
            int_b10k = _from_int(int_val)
            left_groups_str = [g for g in left_frac_str.split('.') if g.strip()]
            right_groups_str = [g for g in right_frac_str.split('.') if g.strip()]
            n = max(len(left_groups_str), len(right_groups_str))
            left_padded = (['0'] * (n - len(left_groups_str)) + left_groups_str
                           if len(left_groups_str) < n else left_groups_str)
            right_padded = (['0'] * (n - len(right_groups_str)) + right_groups_str
                            if len(right_groups_str) < n else right_groups_str)
            frac_le = []
            for i in range(n - 1, -1, -1):
                frac_le.append(int(right_padded[i].lstrip('0') or '0'))
                frac_le.append(int(left_padded[i].lstrip('0') or '0'))
            frac_le = _trim(frac_le) if frac_le else [0]
            combined = _shift_left_abs(int_b10k.digs, 2 * n)
            combined = _add_abs(combined, frac_le)
            return B10K(sign=sign, digs=combined)

        # Старый формат: дробь_левая:целая,дробь_правая (запятая справа)
        # или новый формат: int_L.frac_L: int_R,.frac_R
        right_whole_str, right_frac_str = right_str.split(',', 1)
        left_frac_str = left_str
        int_part_str = right_whole_str

        left_groups_str = [g for g in left_frac_str.split('.') if g.strip()]
        right_groups_str = [g for g in right_frac_str.split('.') if g.strip()]

        # Если слева больше групп — новый формат: первая группа = int_L
        if len(left_groups_str) > len(right_groups_str):
            int_L_str = left_groups_str[0]
            left_groups_str = left_groups_str[1:]  # дробные L
            int_val = int(int_part_str) if int_part_str.strip() else 0
            int_val += int(int_L_str) * BASE
            int_b10k = _from_int(int_val)
        else:
            int_val = int(int_part_str) if int_part_str.strip() else 0
            int_b10k = _from_int(int_val)

        n = max(len(left_groups_str), len(right_groups_str))
        left_padded = (['0'] * (n - len(left_groups_str)) + left_groups_str
                       if len(left_groups_str) < n else left_groups_str)
        right_padded = (['0'] * (n - len(right_groups_str)) + right_groups_str
                        if len(right_groups_str) < n else right_groups_str)

        frac_le = []
        for i in range(n - 1, -1, -1):
            frac_le.append(int(right_padded[i].lstrip('0') or '0'))
            frac_le.append(int(left_padded[i].lstrip('0') or '0'))

        frac_le = _trim(frac_le) if frac_le else [0]
        combined = _shift_left_abs(int_b10k.digs, 2 * n)
        combined = _add_abs(combined, frac_le)
        return B10K(sign=sign, digs=combined)

    # НОВЫЙ ФОРМАТ: int_part, L0.R0.L1.R1.L2.R2...
    comma_pos = s.index(',')
    int_part_str = s[:comma_pos].strip()
    frac_str = s[comma_pos + 1:].strip()

    # Целая часть
    int_val = int(int_part_str) if int_part_str else 0
    int_b10k = _from_int(int_val)

    # Дробная часть: чередование L0, R0, L1, R1, ...
    groups = [g for g in frac_str.split('.') if g.strip()]
    if not groups:
        return int_b10k

    # Чётные индексы → L, нечётные → R
    # L₀, R₀, L₁, R₁, ...
    n_pairs = (len(groups) + 1) // 2  # округление вверх
    left_groups_str = [groups[i] for i in range(0, len(groups), 2)]
    right_groups_str = [groups[i] for i in range(1, len(groups), 2)]

    n = max(len(left_groups_str), len(right_groups_str))
    left_padded = (left_groups_str + ['0'] * (n - len(left_groups_str))
                   if len(left_groups_str) < n else left_groups_str)
    right_padded = (right_groups_str + ['0'] * (n - len(right_groups_str))
                    if len(right_groups_str) < n else right_groups_str)

    frac_le = []
    for i in range(n - 1, -1, -1):
        frac_le.append(int(right_padded[i].lstrip('0') or '0'))
        frac_le.append(int(left_padded[i].lstrip('0') or '0'))

    frac_le = _trim(frac_le) if frac_le else [0]
    combined = _shift_left_abs(int_b10k.digs, 2 * n)
    combined = _add_abs(combined, frac_le)
    return B10K(sign=sign, digs=combined)


def format_num(a: B10K, frac_pairs: int = 0) -> str:
    """
    B10K → строка (переплетающаяся модель).

    По умолчанию (frac_pairs=0): целое число, но если a.frac_pairs > 0,
    используется a.frac_pairs.
    При frac_pairs > 0: выделяет указанное число дробных пар (2×frac_pairs
    LE-элементов как младшие разряды) и форматирует с запятой.

    Формат (целое): L₀.L₁...:R₀.R₁...
      Пример: 0000:0005
    Формат (дробь): int_L.frac_L₀.frac_L₁...:int_R,.frac_R₀.frac_R₁...
      Пример: 0000.1415.3589.3846.3832:0003,.9265.7932.2643.7950
    Порядок групп — от старших разрядов (MSB) к младшим.
    """
    fp = frac_pairs or a.frac_pairs
    if fp > 0:
        return format_frac(a, fp)
    if _is_zero(a):
        return "0000:0000"

    return _format_int(a)


def _format_int(a: B10K) -> str:
    """
    B10K → строка: L₀.L₁.L₂...:R₀.R₁.R₂...
    L-группы (чётные четвёрки) слева от ':', R-группы (нечётные) справа.
    Порядок — от старших разрядов (MSB) к младшим.
    """
    digs = a.digs
    L_groups = []
    R_groups = []
    # LE = [Rₙ₋₁, Lₙ₋₁, ..., R₀, L₀] — LSB→MSB.
    # Идём с конца (MSB) к началу (LSB).
    i = len(digs) - 1
    if i % 2 == 0:
        # Нечётная длина: последний элемент — R без L
        R_groups.append(f"{digs[i]:04d}")
        i -= 1
    while i >= 1:
        r = digs[i - 1]  # Rₖ
        l = digs[i]      # Lₖ
        R_groups.append(f"{r:04d}")
        L_groups.append(f"{l:04d}")
        i -= 2
    # L-групп может быть меньше — дополняем нулями спереди (MSB-конец)
    if len(R_groups) > len(L_groups):
        L_groups = ["0000"] * (len(R_groups) - len(L_groups)) + L_groups
    if not L_groups:
        L_groups.append("0000")
    if not R_groups:
        R_groups.append("0000")
    return f"-{'.'.join(L_groups)}:{'.'.join(R_groups)}" if a.sign == -1 else f"{'.'.join(L_groups)}:{'.'.join(R_groups)}"


# ═══════════════════════════════════════════════════════════
#  ДРОБНЫЕ ЧИСЛА: ПАРСИНГ И ФОРМАТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════

def parse_frac(s: str) -> B10K:
    """
    Парсинг дробного B10K (с запятой).
    Возвращает B10K с frac_pairs, вычисленным из числа точек в дробной части.

    Формат: int_L.frac_L₀.frac_L₁...:int_R,.frac_R₀.frac_R₁...
    или (старый) L₀.L₁...:R₀.R₁...,L₀.L₁...:R₀.R₁...
    L — чётные четвёрки, R — нечётные. Запятая между дробной и целой частью
    (в новом формате — после int_R). Порядок — от младших к старшим.
    """
    b = parse(s)
    # Вычисляем число дробных пар
    comma_pos = s.index(',')
    after_comma = s[comma_pos + 1:]
    if '.' in after_comma:
        groups = [g for g in after_comma.split('.') if g.strip()]
        n_groups = len(groups)
        # Если после запятой сразу идёт точка — формат "int_R,.R0.R1":
        # все группы после запятой — R (по одной на пару).
        if after_comma.lstrip().startswith('.'):
            b.frac_pairs = n_groups
        else:
            # Формат "int_part, L0.R0.L1.R1": чередование L/R.
            b.frac_pairs = (n_groups + 1) // 2
    elif after_comma.strip() == '0':
        # "0,0" — ноль с одной парой
        b.frac_pairs = 1
    else:
        b.frac_pairs = 0
    return b


def _digs_to_dec(digs: List[int], min_pad: int = 0) -> str:
    """B10K LE-цифры → десятичная строка, без Python int.

    Каждая BASE-10000 цифра 0..9999 даёт ровно 4 десятичных разряда
    (кроме самой старшей). LE → LSB→MSB, каждая цифра → 4 цифры,
    последняя (старшая) — без ведущих нулей, затем реверс.

    min_pad — дополнить слева нулями до этой длины.
    """
    if not digs or (len(digs) == 1 and digs[0] == 0):
        return "0".zfill(min_pad) if min_pad else "0"
    parts = []
    for i, d in enumerate(digs):
        if i < len(digs) - 1:
            parts.append(f"{d:04d}")
        else:
            parts.append(str(d))
    s = ''.join(reversed(parts))
    if min_pad and len(s) < min_pad:
        s = s.zfill(min_pad)
    return s


def to_int(a: B10K) -> int:
    """B10K → Python int."""
    if _is_zero(a):
        return 0
    n = sum(d * (BASE ** i) for i, d in enumerate(a.digs))
    return n * a.sign


def to_dec(a: B10K, frac_pairs: Optional[int] = None) -> str:
    """B10K → десятичная строка с точкой для дробных.

    Параметры:
      a — B10K число.
      frac_pairs — число дробных пар (8 десятичных цифр на пару).
                   Если None (по умолчанию), берётся из a.frac_pairs.
                   Если > 0, последние 2*frac_pairs LE-элементов — дробная часть,
                   ставится десятичная точка.

    Примеры:
      to_dec(B("0000:0120"))                  → "120"
      to_dec(pi_b10k(4))                       → "3.14159265358979323846264338327950"
      to_dec(B("-0000:0003"))                  → "-3"
      to_dec(B("-0001:0000"))                  → "-10000"
    """
    if frac_pairs is None:
        frac_pairs = a.frac_pairs
    if frac_pairs is None:
        frac_pairs = 0
    if _is_zero(a):
        if frac_pairs > 0:
            return f"-0.{'0' * (8 * frac_pairs)}" if a.sign == -1 else f"0.{'0' * (8 * frac_pairs)}"
        return "0"

    digs = a.digs

    if frac_pairs > 0:
        n_frac = 2 * frac_pairs
        # LE: младшие элементы = дробная часть, старшие = целая
        frac_digs = digs[:n_frac]
        int_digs = digs[n_frac:]

        # Целая часть
        if int_digs:
            int_str = _digs_to_dec(int_digs)
        else:
            int_str = "0"

        # Дробная часть — каждая пара даёт 8 десятичных цифр
        frac_str = _digs_to_dec(frac_digs, 8 * frac_pairs)

        s = f"{int_str}.{frac_str}"
    else:
        s = _digs_to_dec(digs)

    return f"-{s}" if a.sign == -1 else s


_b10k_to_int = to_int  # обратная совместимость


def format_frac(a: B10K, frac_pairs: int) -> str:
    """
    B10K → строка с дробной частью.

    Формат: int_L.frac_L₀.frac_L₁...:int_R,.frac_R₀.frac_R₁...
    L-группы (чётные четвёрки) слева от ':', R-группы (нечётные) справа.
    Целая часть — первые (самые левые) группы в каждой половине.
    Запятая между целой R-группой и дробными R-группами.

    Пример: 0000.1415.3589.3846.3832:0003,.9265.7932.2643.7950  (π, 4 пары)

    Для дроби: digs[:2*frac_pairs] хранятся как [Rₙ₋₁, Lₙ₋₁, …, R₀, L₀]
    (MSB→LSB pair в LE из-за переворота интерливинга).
    Для целой: digs[2*frac_pairs:] в LE от LSB к MSB.
    """
    if _is_zero(a):
        return "0,0"

    n_frac_le = 2 * frac_pairs
    digs = a.digs

    # Дополняем нулями, если число короче дробной части
    if n_frac_le > len(digs):
        digs = list(digs) + [0] * (n_frac_le - len(digs))

    # ─── Дробные пары: LE хранит [Rₙ₋₁, Lₙ₋₁, …, R₀, L₀] ───
    # Идём с конца — от LSB-пары к MSB-паре.
    frac_L = []
    frac_R = []
    for i in range(n_frac_le - 2, -1, -2):
        r = digs[i]
        l = digs[i + 1]
        frac_R.append(f"{r:04d}")
        frac_L.append(f"{l:04d}")

    # ─── Целые пары: идём с конца (MSB) к началу (LSB) ───
    int_L = []
    int_R = []
    i = len(digs) - 1
    if i >= n_frac_le and (i - n_frac_le) % 2 == 0:
        # Нечётная длина целой части: последний элемент — R без L
        int_R.append(f"{digs[i]:04d}")
        i -= 1
    while i >= n_frac_le:
        # digs[i-1] = R, digs[i] = L
        int_R.append(f"{digs[i - 1]:04d}")
        int_L.append(f"{digs[i]:04d}")
        i -= 2
    # L-групп может быть меньше — дополняем нулями спереди (MSB-конец)
    if len(int_R) > len(int_L):
        int_L = ["0000"] * (len(int_R) - len(int_L)) + int_L

    sign_str = "-" if a.sign == -1 else ""

    # L side: int_L первой, затем дробные L-группы, все разделены точками
    L_str = ".".join(int_L) if int_L else ("0" if not frac_L else "0000")
    if frac_L:
        L_str += "." + ".".join(frac_L)

    # R side: int_R первым, затем запятая+точка, затем дробные R-группы
    R_str = ".".join(int_R) if int_R else "0"
    if frac_R:
        R_str += ",." + ".".join(frac_R)

    return f"{sign_str}{L_str}:{R_str}"


# ─── короткие псевдонимы ──────────────────────────────────

def B(s: str) -> B10K:
    """parse('0000:0005') → B10K."""
    return parse(s)


def _(a: B10K) -> str:
    """format_num."""
    return format_num(a)


# ═══════════════════════════════════════════════════════════
#  REPL-КАЛЬКУЛЯТОР
# ═══════════════════════════════════════════════════════════

def _input_with_history(prompt="", history=None):
    """Ввод строки с поддержкой истории (стрелки вверх/вниз).

    На Unix использует readline. На Windows — ручная обработка через msvcrt.
    """
    import sys as _sys

    if history is None:
        history = []
    _pos = len(history)  # текущая позиция в истории (len = пустая строка)

    # Unix — делегируем readline
    if _sys.platform != 'win32':
        return input(prompt)

    # Windows — ручной ввод
    try:
        import msvcrt
    except ImportError:
        return input(prompt)

    import os as _os
    _buf = []
    while True:
        ch = msvcrt.getwch()
        if ch == '\r':  # Enter
            print()
            line = ''.join(_buf)
            return line
        if ch == '\x03':  # Ctrl+C
            raise KeyboardInterrupt
        if ch == '\x04':  # Ctrl+D
            raise EOFError
        if ch == '\x08' or ch == '\x7f':  # Backspace
            if _buf:
                _buf.pop()
                _sys.stdout.write('\b \b')
                _sys.stdout.flush()
        elif ch == '\xe0':  # Escape-последовательность (стрелки)
            ch2 = msvcrt.getwch()
            if ch2 == 'H':  # Вверх
                if _pos > 0:
                    _pos -= 1
                    _buf = list(history[_pos])
            elif ch2 == 'P':  # Вниз
                if _pos < len(history):
                    _pos += 1
                if _pos == len(history):
                    _buf = []
                else:
                    _buf = list(history[_pos])
            elif ch2 == 'K':  # Влево
                continue  # упрощённо: игнорируем
            elif ch2 == 'M':  # Вправо
                continue
            # перерисовываем строку
            _sys.stdout.write('\r' + prompt + ' ' * 120 + '\r' + prompt)
            _sys.stdout.write(''.join(_buf))
            _sys.stdout.flush()
        elif ch == '\x1b':  # ESC
            continue
        else:
            _buf.append(ch)
            _sys.stdout.write(ch)
            _sys.stdout.flush()


def _repl():
    """Интерактивный калькулятор."""
    _history = []
    print("=== base-10000 REPL ===")
    print("Вводите выражения вида:  0000:0005 + 0000:0003")
    print("Поддерживается: + - * / % ** //")
    print("Функции: fact(n)  gcd(a,b)  lcm(a,b)  isqrt(n)  sqrt(x [,pairs])  tod(n [,pairs])  pi(pairs)")
    print("  pi(10) — пи с 10 парами цифр (80 десятичных); pi() — 10 пар")
    print("  sqrt(x) — целочисленный sqrt; sqrt(x, n) — sqrt с n дробными парами")
    print("  tod(x) — десятичная строка; tod(x, 4) — с дробной точкой (4 пары)")
    print("  e(pairs) — Эйлерово число e (pairs = число пар)")
    print("  fib(n) — число Фибоначчи F(n)")
    print("  sin(x, pairs) — синус (радианы); cos(x, pairs) — косинус")
    print("  tan(x, pairs) — тангенс; atan(x, pairs) — арктангенс")
    print("  exp(x, pairs) — e^x; ln(x, pairs) — натуральный логарифм")
    print("  log(x, pairs) — десятичный логарифм")
    print("Переменные: обозначаются буквами, сохраняются через =")
    print("  x = 0000:0100")
    print("  x * x")
    print("Формат вывода: $fmt = dec | b10k | auto (по умолчанию)")
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
    _fmt_mode = 'auto'  # 'auto' | 'b10k' | 'dec'

    def eval_expr(tokens):
        """Simple expression evaluator: function(args), a op b, variable, or literal."""
        nonlocal _fmt_mode
        if not tokens:
            return None

        # Присваивание: name = expr
        if len(tokens) >= 3 and tokens[1] == '=':
            name = tokens[0]
            # $fmt — специальная переменная формата вывода (не identifier)
            if name == '$fmt':
                mode = tokens[2].lower()
                if mode in ('b10k', 'dec', 'auto'):
                    _fmt_mode = mode
                    print(f"  формат: {mode}")
                else:
                    print(f"  допустимо: b10k, dec, auto")
                return None
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
            # Найти парную закрывающую скобку (учёт вложенности)
            depth = 1
            close_idx = None
            for i in range(2, len(tokens)):
                if tokens[i] == '(':
                    depth += 1
                elif tokens[i] == ')':
                    depth -= 1
                    if depth == 0:
                        close_idx = i
                        break
            if close_idx is None:
                print("  несбалансированные скобки")
                return None

            func_name = tokens[0]
            raw_args = tokens[2:close_idx]

            # Разделить аргументы по запятым (вне скобок)
            args = []
            cur = []
            d = 0
            for t in raw_args:
                if t == ',' and d == 0:
                    v = eval_expr(cur)
                    if v is None:
                        return None
                    args.append(v)
                    cur = []
                else:
                    if t == '(':
                        d += 1
                    elif t == ')':
                        d -= 1
                    cur.append(t)
            if cur:
                v = eval_expr(cur)
                if v is None:
                    return None
                args.append(v)

            # остаток выражения после )
            rest = eval_expr(tokens[close_idx + 1:])

            if func_name == 'fact':
                if len(args) < 1:
                    print("  fact(n [, m, ...]) — факториал n! или дробный")
                    return None
                result = fact(args[0], *args[1:])
            elif func_name == 'gcd':
                result = gcd(args[0], args[1])
            elif func_name == 'lcm':
                result = lcm(args[0], args[1])
            elif func_name == 'isqrt':
                result = isqrt(args[0])
            elif func_name == 'sqrt':
                if len(args) == 1:
                    result = sqrt_b10k(args[0])
                elif len(args) == 2:
                    result = sqrt_b10k(args[0], to_int(args[1]))
                else:
                    print("  sqrt(x [, pairs]) — квадратный корень с pairs дробными парами")
                    return None
            elif func_name in ('tod', 'to_dec'):
                # tod(x) или tod(x, pairs)
                if len(args) == 1:
                    result = to_dec(args[0])
                elif len(args) == 2:
                    result = to_dec(args[0], frac_pairs=to_int(args[1]))
                else:
                    print("  tod(x [, pairs]) — конвертация B10K в десятичную строку")
                    return None
                print(f"  {result}")
                return None
            elif func_name == 'pi':
                pi_pairs = 10
                if len(args) == 1:
                    pi_pairs = to_int(args[0])
                elif len(args) > 1:
                    print("  pi([pairs]) — число пар (по умолчанию 10)")
                    return None
                if pi_pairs < 1:
                    pi_pairs = 1
                result = pi_b10k(pi_pairs)
                return result
            elif func_name == 'fib':
                if len(args) != 1:
                    print("  fib(n) — число Фибоначчи F(n)")
                    return None
                result = fib_b10k(args[0])
            elif func_name == 'e':
                e_pairs = 10
                if len(args) == 1:
                    e_pairs = to_int(args[0])
                elif len(args) > 1:
                    print("  e([pairs]) — число пар (по умолчанию 10)")
                    return None
                if e_pairs < 1:
                    e_pairs = 1
                result = e_b10k(e_pairs)
                return result
            elif func_name == 'sin':
                if len(args) == 1:
                    result = sin_b10k(args[0])
                elif len(args) == 2:
                    result = sin_b10k(args[0], to_int(args[1]))
                else:
                    print("  sin(x [, pairs]) — синус x радиан с pairs парами")
                    return None
            elif func_name == 'cos':
                if len(args) == 1:
                    result = cos_b10k(args[0])
                elif len(args) == 2:
                    result = cos_b10k(args[0], to_int(args[1]))
                else:
                    print("  cos(x [, pairs]) — косинус x радиан с pairs парами")
                    return None
            elif func_name == 'tan':
                if len(args) == 1:
                    result = tan_b10k(args[0])
                elif len(args) == 2:
                    result = tan_b10k(args[0], to_int(args[1]))
                else:
                    print("  tan(x [, pairs]) — тангенс x с pairs парами")
                    return None
            elif func_name == 'atan':
                if len(args) == 1:
                    result = atan_b10k(args[0])
                elif len(args) == 2:
                    result = atan_b10k(args[0], to_int(args[1]))
                else:
                    print("  atan(x [, pairs]) — арктангенс с pairs парами")
                    return None
            elif func_name == 'exp':
                if len(args) == 1:
                    result = exp_b10k(args[0])
                elif len(args) == 2:
                    result = exp_b10k(args[0], to_int(args[1]))
                else:
                    print("  exp(x [, pairs]) — e^x с pairs парами")
                    return None
            elif func_name == 'ln':
                if len(args) == 1:
                    result = ln_b10k(args[0])
                elif len(args) == 2:
                    result = ln_b10k(args[0], to_int(args[1]))
                else:
                    print("  ln(x [, pairs]) — натуральный логарифм")
                    return None
            elif func_name == 'log':
                if len(args) == 1:
                    result = log10_b10k(args[0])
                elif len(args) == 2:
                    result = log10_b10k(args[0], to_int(args[1]))
                else:
                    print("  log(x [, pairs]) — десятичный логарифм")
                    return None
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
                line = _input_with_history("b10k> ", _history).strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line in ('.exit', '.quit', 'exit', 'quit'):
                break

            _history.append(line)

            try:
                # чистим BOM и непечатные символы (PowerShell)
                while line and not (line[0].isdigit() or line[0] in '-.:$' or line[0].isalpha()):
                    line = line[1:]
                line = line.strip()
                # разбиваем на токены, сохраняя скобки
                tokens = line.replace('(', ' ( ').replace(')', ' ) ').replace('=', ' = ')
                tokens = tokens.replace(',', ' , ')
                tokens = [t for t in tokens.split() if t]

                result = eval_expr(tokens)
                if result is not None:
                    if _fmt_mode == 'b10k':
                        print(f"  {format_num(result)}")
                    elif _fmt_mode == 'dec':
                        print(f"  {to_dec(result)}")
                    else:  # auto
                        fp = result.frac_pairs if hasattr(result, 'frac_pairs') else 0
                        if fp > 0:
                            print(f"  {to_dec(result)}")
                        else:
                            print(f"  {format_num(result)}")
            except Exception as e:
                print(f"  ошибка: {e}")

    except KeyboardInterrupt:
        print()
    print("Пока!")


def _arctan_scaled_b10k(x: B10K, x_sq: int, S: B10K) -> B10K:
    """Вычислить arctan(1/x) × S через ряд (B10K-арифметика).

    Ряд: arctan(1/x) = 1/x - 1/(3·x³) + 1/(5·x⁵) - 1/(7·x⁷) + …

    x_sq — Python int (маленький делитель, деление O(n)).
    S — B10K, содержит масштаб BASE^(2·(pairs+1)).
    """
    # S / x как B10K (первое деление — полноценное, x может быть многозначным)
    numerator = div(S, x)
    result = _zero()
    k = 0
    while not _is_zero(numerator):
        # term = numerator // (2k+1) — маленький делитель
        t_digs = _div_small_abs(numerator.digs, 2 * k + 1)
        term = B10K(sign=1, digs=t_digs) if t_digs != [0] else _zero()

        if k % 2 == 0:
            result = add(result, term)
        else:
            result = sub(result, term)

        # numerator //= x_sq — маленький делитель
        numerator = B10K(sign=1, digs=_div_small_abs(numerator.digs, x_sq))
        k += 1
    return result


def pi_b10k(pairs: int = 20) -> B10K:
    """Вычислить π как B10K с заданным числом пар цифр.

    Формула Machin: π = 16·arctg(1/5) − 4·arctg(1/239)
    Все вычисления — через B10K-арифметику.

    Каждая пара даёт 2 группы по 4 десятичных цифры,
    то есть 8 десятичных цифр π на пару.
    Пример: pi(4) → 32 десятичных цифры π.

    В REPL: pi(10) — 10 пар (80 десятичных цифр).
    """
    # Считаем с одной запасной парой для округления
    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))

    x5 = _from_int(5)
    x239 = _from_int(239)
    a5 = _arctan_scaled_b10k(x5, 25, S)        # x_sq — int, малый делитель
    a239 = _arctan_scaled_b10k(x239, 57121, S)

    # π × S = 16·a5 − 4·a239
    result = sub(mul(_from_int(16), a5), mul(_from_int(4), a239))

    # Отбросить запасную пару: сдвинуть LE-массив вправо на 2 цифры
    result = B10K(sign=result.sign, digs=_shift_right_abs(result.digs, 2),
                  frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)

    return result


# ═══════════════════════════════════════════════════════════
#  НОВЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════

def fib_b10k(n: B10K) -> B10K:
    """Число Фибоначчи F(n), быстрый метод удвоения O(log n).

    F(2k)   = F(k)·(2·F(k+1) − F(k))
    F(2k+1) = F(k+1)² + F(k)²

    n >= 0.  n=0 → 0, n=1 → 1.
    """
    if _is_zero(n) or n.sign < 0:
        return _zero()
    k = to_int(n)
    if k < 0:
        return _zero()

    def _fib_pair(k: int) -> Tuple[B10K, B10K]:
        """(F(k), F(k+1))"""
        if k == 0:
            return (_zero(), _from_int(1))
        fa, fb = _fib_pair(k >> 1)
        # c = F(2k)   = fa·(2·fb − fa)
        # d = F(2k+1) = fb² + fa²
        c = mul(fa, sub(mul(_from_int(2), fb), fa))
        d = add(mul(fb, fb), mul(fa, fa))
        if k & 1 == 0:
            return (c, d)
        else:
            return (d, add(c, d))

    return _fib_pair(k)[0]


def e_b10k(pairs: int = 10) -> B10K:
    """Вычислить e (основание натурального логарифма) как B10K.

    Ряд: e = Σ_{k=0}^{∞} 1/k!
    Вычисляется в масштабе S = BASE^(2·(pairs+1)) с помощью
    _div_small_abs (O(n) на итерацию).

    Пример: e_b10k(4) — e с 4 парами (32 десятичных цифры).
    """
    # Масштаб: S = BASE^(2·(pairs+1))
    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))

    result = S  # k=0: 1/0! × S = S
    term = S
    k = 1
    while True:
        term = B10K(sign=1, digs=_div_small_abs(term.digs, k))
        if _is_zero(term):
            break
        result = add(result, term)
        k += 1

    # Отбросить запасную пару
    result = B10K(sign=1, digs=_shift_right_abs(result.digs, 2),
                  frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def sin_b10k(x: B10K, pairs: int = 10) -> B10K:
    """sin(x) с точностью до `pairs` дробных пар.

    Ряд Тейлора  sin(x) = x − x³/3! + x⁵/5! − x⁷/7! + …
    x может быть B10K с frac_pairs (дробное значение) или целым (радианы).

    Пример: sin(B("0000:0001"), 10) — sin(1 rad) с 10 парами.
            sin(pi_b10k(10), 10) — sin(π) с 10 парами (должно быть ≈0).
    """
    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))
    fp = x.frac_pairs if hasattr(x, 'frac_pairs') and x.frac_pairs else 0

    # x_scaled = x_val · S
    x_times_S = mul(x, S)
    if fp > 0:
        x_scaled = B10K(sign=x.sign,
                        digs=_shift_right_abs(x_times_S.digs, 2 * fp))
    else:
        x_scaled = x_times_S

    if _is_zero(x_scaled):
        return B10K(sign=1, digs=[0], frac_pairs=pairs)

    # x_sq = x_val² — при fp>0 масштаб BASE^(4·fp)
    x_sq = mul(x, x)

    result = _zero()
    term = x_scaled  # k=1: x · S
    k = 1

    while True:
        result = add(result, term)

        # term_{k+1} = −term_k · x² / ((2k)(2k+1))
        temp = mul(term, x_sq)   # scale: S × BASE^(4·fp)
        if _is_zero(temp):
            break
        temp = neg(temp)
        temp = B10K(sign=temp.sign,
                    digs=_div_small_abs(temp.digs, 2 * k))
        temp = B10K(sign=temp.sign,
                    digs=_div_small_abs(temp.digs, 2 * k + 1))
        # Деление на масштаб x_sq, если x дробный
        if fp > 0:
            temp = B10K(sign=temp.sign,
                        digs=_shift_right_abs(temp.digs, 4 * fp))
        term = temp
        k += 1

        if _is_zero(term):
            break

    # Отбросить запасную пару
    result = B10K(sign=result.sign,
                  digs=_shift_right_abs(result.digs, 2),
                  frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def cos_b10k(x: B10K, pairs: int = 10) -> B10K:
    """cos(x) с точностью до `pairs` дробных пар.

    Ряд Тейлора  cos(x) = 1 − x²/2! + x⁴/4! − x⁶/6! + …
    """
    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))
    fp = x.frac_pairs if hasattr(x, 'frac_pairs') and x.frac_pairs else 0

    # x_scaled = x_val · S
    x_times_S = mul(x, S)
    if fp > 0:
        x_scaled = B10K(sign=x.sign,
                        digs=_shift_right_abs(x_times_S.digs, 2 * fp))
    else:
        x_scaled = x_times_S

    # x_sq = x_val²
    x_sq = mul(x, x)

    if _is_zero(x_scaled):
        # cos(0) = 1  →  результат = 1 × S, отбрасываем запасную пару
        return B10K(sign=1, digs=_shift_right_abs(list(S.digs), 2),
                    frac_pairs=pairs)

    result = _zero()
    # k=0: 1 × S (единица в масштабе S)
    term = B10K(sign=1, digs=list(S.digs))
    k = 1

    while True:
        result = add(result, term)

        # term_{k+1} = −term_k · x² / ((2k−1)(2k))
        temp = mul(term, x_sq)
        if _is_zero(temp):
            break
        temp = neg(temp)
        temp = B10K(sign=temp.sign,
                    digs=_div_small_abs(temp.digs, 2 * k - 1))
        temp = B10K(sign=temp.sign,
                    digs=_div_small_abs(temp.digs, 2 * k))
        if fp > 0:
            temp = B10K(sign=temp.sign,
                        digs=_shift_right_abs(temp.digs, 4 * fp))
        term = temp
        k += 1

        if _is_zero(term):
            break

    result = B10K(sign=result.sign,
                  digs=_shift_right_abs(result.digs, 2),
                  frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def tan_b10k(x: B10K, pairs: int = 10) -> B10K:
    """tan(x) = sin(x)/cos(x) с точностью pairs дробных пар."""
    s = sin_b10k(x, pairs + 1)
    c = cos_b10k(x, pairs + 1)
    if _is_zero(c):
        raise ValueError("tan(x): asimptota (cos ~ 0)")
    # s и c имеют frac_pairs = pairs+1.
    # div(s, c) даёт floor(tan(x)) — теряем дробную часть при |tan|<1.
    # Умножаем s.digs на 10000^(2*pairs) перед делением,
    # чтобы result.digs ~ tan(x) * 10000^(2*pairs), frac_pairs = pairs.
    S = pow_b10k(_from_int(BASE), _from_int(2 * pairs))
    t = div(mul(s, S), c)
    return B10K(sign=t.sign, digs=t.digs, frac_pairs=pairs)


def atan_b10k(x: B10K, pairs: int = 10) -> B10K:
    """arctg(x) через ряд Тейлора с S-масштабированием.

    atan(x) = x − x³/3 + x⁵/5 − x⁷/7 + …
    Для |x| > 1: atan(x) = π/2 − atan(1/x)
    """
    if x.sign < 0:
        return neg(atan_b10k(neg(x), pairs))
    one = _from_int(1)
    if _cmp_abs(x.digs, one.digs) > 0:  # |x| > 1
        inv = div(one, x)
        half_pi = div(pi_b10k(pairs + 1), _from_int(2))
        a = atan_b10k(inv, pairs + 1)
        r = sub(half_pi, a)
        return B10K(sign=r.sign, digs=_shift_right_abs(r.digs, 2), frac_pairs=pairs)
    if _cmp_abs(x.digs, one.digs) == 0 and (not hasattr(x, 'frac_pairs') or x.frac_pairs == 0):
        # atan(1) = π/4  — прямой результат, избегаем медленного ряда
        q = div(pi_b10k(pairs + 1), _from_int(4))
        return B10K(sign=q.sign, digs=_shift_right_abs(q.digs, 2), frac_pairs=pairs)

    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))
    fp = x.frac_pairs if hasattr(x, 'frac_pairs') and x.frac_pairs else 0
    x_times_S = mul(x, S)
    if fp > 0:
        x_scaled = B10K(sign=x.sign, digs=_shift_right_abs(x_times_S.digs, 2 * fp))
    else:
        x_scaled = x_times_S
    x_sq = mul(x, x)
    if _is_zero(x_scaled):
        return B10K(sign=1, digs=[0], frac_pairs=pairs)

    result = _zero()
    term = x_scaled  # k=0: x·S
    k = 0
    while True:
        result = add(result, term) if k % 2 == 0 else sub(result, term)
        temp = mul(term, x_sq)
        if _is_zero(temp):
            break
        temp = B10K(sign=temp.sign, digs=_mul_small(temp.digs, 2 * k + 1))
        temp = B10K(sign=temp.sign, digs=_div_small_abs(temp.digs, 2 * k + 3))
        temp = neg(temp)
        if fp > 0:
            temp = B10K(sign=temp.sign, digs=_shift_right_abs(temp.digs, 4 * fp))
        term = temp
        k += 1
        if _is_zero(term):
            break

    result = B10K(sign=result.sign, digs=_shift_right_abs(result.digs, 2), frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def exp_b10k(x: B10K, pairs: int = 10) -> B10K:
    """e^x через ряд Тейлора с S-масштабированием.

    e^x = Σ x^k/k!  (k = 0…∞)
    """
    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))
    fp = x.frac_pairs if hasattr(x, 'frac_pairs') and x.frac_pairs else 0
    x_times_S = mul(x, S)
    if fp > 0:
        x_scaled = B10K(sign=x.sign, digs=_shift_right_abs(x_times_S.digs, 2 * fp))
    else:
        x_scaled = x_times_S

    result = S  # k=0: 1·S
    term = S    # term_0 = 1·S
    k = 1
    while True:
        # term_k = term_{k-1} · x / k
        temp = mul(term, x_scaled)
        if _is_zero(temp):
            break
        temp = B10K(sign=temp.sign, digs=_div_small_abs(temp.digs, k))
        # temp сейчас = S · x^k/k!  (если x целый)
        # Если x дробный, temp = S · x^k/k! · BASE^(2·fp·(k-1))
        if fp > 0 and k > 1:
            temp = B10K(sign=temp.sign, digs=_shift_right_abs(temp.digs, 2 * fp * (k - 1)))
        term = temp
        result = add(result, term)
        k += 1
        if _is_zero(term):
            break

    result = B10K(sign=result.sign, digs=_shift_right_abs(result.digs, 2), frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def ln_b10k(x: B10K, pairs: int = 10) -> B10K:
    """ln(x) — натуральный логарифм.

    Для x ≤ 0: ValueError.
    Для x ≈ 1: ряд ln(1+t) = t − t²/2 + t³/3 − t⁴/4 + …  (t = x−1)
    В остальных случаях: ln(x) = ln(x/10^k) + k·ln(10) с редукцией.
    """
    if x.sign < 0 or _is_zero(x):
        raise ValueError("ln(x): x должно быть > 0")
    one = _from_int(1)
    if _cmp_abs(x.digs, one.digs) == 0 and (not hasattr(x, 'frac_pairs') or x.frac_pairs == 0):
        return _zero()  # ln(1) = 0

    # Редукция: находим k такое, что 1 ≤ x/10^k < 10
    # В B10K-формате: x = m·10^{4·k} где m = x>>(2k) (k пар)
    # Упрощённо: через десятичную длину
    s = to_dec(x) if x.frac_pairs == 0 else to_dec(x, x.frac_pairs)
    if '.' in s:
        s_int = s.split('.')[0] if s.startswith('-') else s.split('.')[0]
    else:
        s_int = s
    s_int = s_int.lstrip('-')
    # Число десятичных разрядов целой части
    int_digits = len(s_int) if s_int != '0' else 0

    # ln(10) ≈ 2.3025850929940456840
    ln10 = parse_frac("2,3025.8509.2994.0456.8401")
    if int_digits <= 1:
        # x уже в диапазоне [1, 10) — используем ряд ln(1+t)
        return _ln_via_series(x, pairs)
    else:
        # x = m·10^k
        k = int_digits - 1
        # m = x // 10^k в десятичной арифметике
        pow10 = _from_int(10 ** k)
        m = div(x, pow10)
        ln_m = _ln_via_series(m, pairs + 1)
        ln_pow = mul(ln10, _from_int(k))
        r = add(ln_m, ln_pow)
        return B10K(sign=r.sign, digs=_shift_right_abs(r.digs, 2), frac_pairs=pairs)


def _ln_via_series(x: B10K, pairs: int) -> B10K:
    """ln(x) для x ≈ 1 через ряд ln(1+t) с S-масштабированием."""
    one = _from_int(1)
    t = sub(x, one)  # t = x − 1
    if _is_zero(t):
        return B10K(sign=1, digs=[0], frac_pairs=pairs)

    S = pow_b10k(_from_int(BASE), _from_int(2 * (pairs + 1)))
    fp = t.frac_pairs if hasattr(t, 'frac_pairs') and t.frac_pairs else 0

    t_times_S = mul(t, S)
    if fp > 0:
        t_scaled = B10K(sign=t.sign, digs=_shift_right_abs(t_times_S.digs, 2 * fp))
    else:
        t_scaled = t_times_S
    t_sq = mul(t, t)

    if _is_zero(t_scaled):
        return B10K(sign=1, digs=[0], frac_pairs=pairs)

    result = _zero()
    term = t_scaled  # k=1: t·S
    k = 1
    while True:
        # term_k = (-1)^(k-1)·t^k/k·S
        if k % 2 == 1:
            result = add(result, term)
        else:
            result = sub(result, term)

        # term_{k+1} = term_k · t · k/(k+1)
        temp = mul(term, t) if k >= 1 else mul(term, t_scaled)
        if _is_zero(temp):
            break
        if k >= 1:
            temp = B10K(sign=temp.sign, digs=_mul_small(temp.digs, k))
            temp = B10K(sign=temp.sign, digs=_div_small_abs(temp.digs, k + 1))
        if fp > 0 and k > 0:
            temp = B10K(sign=temp.sign, digs=_shift_right_abs(temp.digs, 2 * fp))
        term = temp
        k += 1
        if _is_zero(term):
            break

    result = B10K(sign=result.sign, digs=_shift_right_abs(result.digs, 2), frac_pairs=pairs)
    if not result.digs:
        result = B10K(sign=1, digs=[0], frac_pairs=pairs)
    return result


def log10_b10k(x: B10K, pairs: int = 10) -> B10K:
    """log10(x) = ln(x)/ln(10)."""
    # ln(10) ≈ 2.3025850929940456840
    ln10 = parse_frac("2,3025.8509.2994.0456.8401")
    ln_pairs = pairs + 2
    ln_x = ln_b10k(x, ln_pairs)
    ln10_val = ln_b10k(_from_int(10), ln_pairs)
    r = div(ln_x, ln10_val)
    return B10K(sign=r.sign, digs=_shift_right_abs(r.digs, 2 * 2), frac_pairs=pairs)


# Публичный entry point для REPL (используется в b10k CLI)
main_repl = _repl

if __name__ == "__main__":
    import sys
    # По умолчанию — REPL; --test для тестов
    if '--test' in sys.argv:
        pass  # ниже тесты
    else:
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
