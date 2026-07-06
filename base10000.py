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


def fact(n: B10K, *extra: B10K) -> B10K:
    """n! (факториал).

    Один аргумент: обычный факториал n!.
    Два аргумента: дробный B10K, где целая часть = fact(n),
    дробные группы = факториалы extra аргументов, разбитые на B10K-группы.
    Пример: fact(4, 769) → целая часть 24, дробная = fact(769) в base-10000
    """
    if n.sign == -1:
        raise ValueError("факториал отрицательного")
    if _is_zero(n) or (len(n.digs) == 1 and n.digs[0] == 1):
        int_result = _from_int(1)
    else:
        int_result = _from_int(1)
        i = _from_int(2)
        one = _from_int(1)
        while i <= n:
            int_result = mul(int_result, i)
            i = add(i, one)

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
    """Парсинг целого B10K (без запятой)."""
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
            be = []
            for i in range(n):
                be.append(int(left_padded[i].lstrip('0') or '0'))
                be.append(int(right_padded[i].lstrip('0') or '0'))
            frac_le = list(reversed(be))
            frac_le = _trim(frac_le) if frac_le else [0]
            combined = _shift_left_abs(int_b10k.digs, 2 * n)
            combined = _add_abs(combined, frac_le)
            return B10K(sign=sign, digs=combined)

        # Старый формат: дробь_левая:целая,дробь_правая (запятая справа)
        right_whole_str, right_frac_str = right_str.split(',', 1)
        left_frac_str = left_str
        int_part_str = right_whole_str

        int_val = int(int_part_str) if int_part_str.strip() else 0
        int_b10k = _from_int(int_val)

        left_groups_str = [g for g in left_frac_str.split('.') if g.strip()]
        right_groups_str = [g for g in right_frac_str.split('.') if g.strip()]

        n = max(len(left_groups_str), len(right_groups_str))
        left_padded = (['0'] * (n - len(left_groups_str)) + left_groups_str
                       if len(left_groups_str) < n else left_groups_str)
        right_padded = (['0'] * (n - len(right_groups_str)) + right_groups_str
                        if len(right_groups_str) < n else right_groups_str)

        be = []
        for i in range(n):
            be.append(int(left_padded[i].lstrip('0') or '0'))
            be.append(int(right_padded[i].lstrip('0') or '0'))

        frac_le = list(reversed(be))
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
    left_padded = (['0'] * (n - len(left_groups_str)) + left_groups_str
                   if len(left_groups_str) < n else left_groups_str)
    right_padded = (['0'] * (n - len(right_groups_str)) + right_groups_str
                    if len(right_groups_str) < n else right_groups_str)

    be = []
    for i in range(n):
        be.append(int(left_padded[i].lstrip('0') or '0'))
        be.append(int(right_padded[i].lstrip('0') or '0'))

    frac_le = list(reversed(be))
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

    Формат (целое): 0000:0003
    Формат (дробь): int_part, L0.R0.L1.R1...
      Пример: 3,1415.9265.3589.7932.3846.2643
    """
    fp = frac_pairs or a.frac_pairs
    if fp > 0:
        return format_frac(a, fp)
    if _is_zero(a):
        return "0000:0000"

    return _format_int(a)


def _format_int(a: B10K) -> str:
    """B10K → строка (целое число)."""
    # Little-endian → Big-endian
    be = list(reversed(a.digs))

    # Дополняем до чётного числа групп
    if len(be) % 2 != 0:
        be.insert(0, 0)

    # Чётные индексы → левая половина, нечётные → правая
    left = [f"{be[i]:04d}" for i in range(0, len(be), 2)]
    right = [f"{be[i + 1]:04d}" for i in range(0, len(be), 2)]

    s = ".".join(left) + ":" + ".".join(right)
    return f"-{s}" if a.sign == -1 else s


# ═══════════════════════════════════════════════════════════
#  ДРОБНЫЕ ЧИСЛА: ПАРСИНГ И ФОРМАТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════

def parse_frac(s: str) -> B10K:
    """
    Парсинг дробного B10K (с запятой).
    Возвращает B10K с frac_pairs, вычисленным из числа точек в дробной части.

    Формат: int_part, L0.R0.L1.R1.L2.R2...
    """
    b = parse(s)
    # Вычисляем число дробных пар: (число точек после запятой + 1) // 2
    comma_pos = s.index(',')
    after_comma = s[comma_pos + 1:]
    if '.' in after_comma:
        n_dots = after_comma.count('.')
        n_groups = n_dots + 1  # групп после запятой
        b.frac_pairs = (n_groups + 1) // 2  # с округлением вверх
    elif after_comma.strip() == '0':
        # "0,0" — ноль с одной парой
        b.frac_pairs = 1
    else:
        b.frac_pairs = 0
    return b


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
            int_n = sum(d * (BASE ** i) for i, d in enumerate(int_digs))
            int_str = str(int_n)
        else:
            int_str = "0"

        # Дробная часть — каждая пара даёт 8 десятичных цифр
        frac_n = sum(d * (BASE ** i) for i, d in enumerate(frac_digs))
        frac_str = str(frac_n).zfill(8 * frac_pairs)

        s = f"{int_str}.{frac_str}"
    else:
        n = sum(d * (BASE ** i) for i, d in enumerate(digs))
        s = str(n)

    return f"-{s}" if a.sign == -1 else s


_b10k_to_int = to_int  # обратная совместимость


def format_frac(a: B10K, frac_pairs: int) -> str:
    """
    B10K → строка с дробной частью (чередование L0.R0.L1.R1...).

    Целая часть — десятичное число, дробная — чередование левых и правых
    4-циферных групп: каждая пара (L,R) = 8 десятичных цифр.

    Примеры:
      format_frac(pi, 6) → "3,1415.9265.3589.7932.3846.2643"
      format_frac(a, 4)  → "6,7082.2039.0892.1006"
    """
    if _is_zero(a):
        return "0,0"

    n_frac_le = 2 * frac_pairs  # число LE-элементов в дробной части
    n_le = len(a.digs)

    if n_frac_le >= n_le:
        # Целая часть = 0
        int_str = "0"
        pad = [0] * (n_frac_le - n_le)
        frac_digs_rev = list(reversed(pad + a.digs))
    else:
        int_digs = a.digs[n_frac_le:]
        frac_digs = a.digs[:n_frac_le]

        # Целая часть — десятичное число
        int_val = 0
        for i, g in enumerate(int_digs):
            int_val += g * (BASE ** i)
        int_str = str(int_val)

        frac_digs_rev = list(reversed(frac_digs))

    # BE → десятичные цифры дробной части: pad4, concat, lstrip('0')
    frac_dec = ''.join(f"{g:04d}" for g in frac_digs_rev).lstrip('0')
    if not frac_dec:
        frac_dec = '0'

    # Группируем десятичные цифры СПРАВА по 8 (алгоритм «с младших разрядов»)
    chunks = []
    i = len(frac_dec)
    while i > 0:
        start = max(0, i - 8)
        chunks.append(frac_dec[start:i])
        i = start

    # Каждая 8-ка → (L, R), выводим как L0.R0.L1.R1...
    pairs = []
    for chunk in reversed(chunks):
        chunk = chunk.zfill(8)
        pairs.append(chunk[:4])  # L
        pairs.append(chunk[4:])  # R

    # Первая группа — без ведущих нулей
    if pairs:
        pairs[0] = pairs[0].lstrip('0') or '0'

    sign_str = "-" if a.sign == -1 else ""
    return f"{sign_str}{int_str},{'.'.join(pairs)}"


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
    print("Функции: fact(n)  gcd(a,b)  lcm(a,b)  isqrt(n)  tod(n [,pairs])  pi(pairs)")
    print("  pi(10) — π с 10 парами цифр (80 десятичных); pi() — 10 пар")
    print("  tod(x) — десятичная строка; tod(x, 4) — с дробной точкой (4 пары)")
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
                pi_pairs = 20
                if len(args) == 1:
                    pi_pairs = to_int(args[0])
                    if pi_pairs < 1:
                        pi_pairs = 20
                elif len(args) > 1:
                    print("  pi([pairs]) — число пар (по умолчанию 20)")
                    return None
                result = pi_b10k(pi_pairs)
                s = format_num(result, frac_pairs=pi_pairs)
                print(f"  {s}")
                return result
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


# Публичный entry point для REPL (используется в b10k CLI)
main_repl = _repl

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
