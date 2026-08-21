import math
from fractions import Fraction


class LongDouble:
    """模拟 C 语言的 long double (80位扩展精度)"""

    EXP_BIAS = 16383
    EXP_BITS = 15
    MANT_BITS = 64

    def __init__(self, value=0.0):
        self.data = bytearray(16)
        if isinstance(value, str):
            self._from_string(value)
        elif isinstance(value, (float, int)):
            self._from_float(float(value))
        elif isinstance(value, LongDouble):
            self.data = bytearray(value.data)
        else:
            raise TypeError("只支持 float、int、str 或 LongDouble")

    # ---------- 字符串解析（使用 Fraction 精确转换） ----------
    def _from_string(self, s):
        try:
            frac = Fraction(s)  # 自动处理正负号、整数、小数、科学计数法
        except Exception:
            raise ValueError(f"无效的数字字符串: '{s}'")

        if frac == 0:
            self._set_bits(0, 0, 0)
            return

        sign = 0 if frac > 0 else 1
        frac = abs(frac)

        # 将分数转换为定点整数： frac * 2^64
        scaled = (frac.numerator << self.MANT_BITS) // frac.denominator
        if scaled == 0:
            self._set_bits(sign, 0, 0)
            return

        # 规格化到 [2^64, 2^65) 之间，使得 (temp / 2^64) 在 [1, 2) 内
        exp = 0
        temp = scaled
        # 如果 temp >= 2^65，右移
        while temp >= (1 << (self.MANT_BITS + 1)):
            temp >>= 1
            exp += 1
        # 如果 temp < 2^64，左移
        while temp < (1 << self.MANT_BITS):
            temp <<= 1
            exp -= 1
        # 现在 temp 在 [2^64, 2^65)，去掉隐含的 2^64
        mantissa = temp - (1 << self.MANT_BITS)
        result_exp = exp + self.EXP_BIAS

        if result_exp >= 0x7FFF:
            self._set_bits(sign, 0x7FFF, 0)
            return
        if result_exp <= 0:
            self._set_bits(sign, 0, 0)
            return
        self._set_bits(sign, result_exp, mantissa)

    # ---------- 从 float 转换 ----------
    def _from_float(self, value):
        sign = 1 if math.copysign(1.0, value) < 0 else 0
        if value == 0.0:
            self._set_bits(sign, 0, 0)
            return
        abs_val = abs(value)
        if math.isinf(abs_val):
            self._set_bits(sign, (1 << self.EXP_BITS) - 1, 0)
            return
        if math.isnan(abs_val):
            self._set_bits(sign, (1 << self.EXP_BITS) -
                           1, 1 << (self.MANT_BITS - 1))
            return

        mant, exp = math.frexp(abs_val)
        if mant < 1.0:
            mant *= 2.0
            exp -= 1
        exponent = exp + self.EXP_BIAS
        mantissa = int((mant - 1.0) * (1 << self.MANT_BITS))
        mantissa &= ((1 << self.MANT_BITS) - 1)
        self._set_bits(sign, exponent, mantissa)

    def _set_bits(self, sign, exponent, mantissa):
        self.data = bytearray(16)
        for i in range(8):
            self.data[i] = (mantissa >> (i * 8)) & 0xFF
        self.data[8] = exponent & 0xFF
        self.data[9] = ((exponent >> 8) & 0x7F) | (sign << 7)

    def _get_bits(self):
        sign = (self.data[9] >> 7) & 1
        exponent = ((self.data[9] & 0x7F) << 8) | self.data[8]
        mantissa = 0
        for i in range(7, -1, -1):
            mantissa = (mantissa << 8) | self.data[i]
        return sign, exponent, mantissa

    def to_float(self):
        sign, exponent, mantissa = self._get_bits()
        if exponent == 0:
            if mantissa == 0:
                return -0.0 if sign else 0.0
            value = mantissa / (1 << self.MANT_BITS) * \
                (2 ** (1 - self.EXP_BIAS))
        elif exponent == (1 << self.EXP_BITS) - 1:
            if mantissa == 0:
                return -float('inf') if sign else float('inf')
            else:
                return float('nan')
        else:
            value = (1.0 + mantissa / (1 << self.MANT_BITS)) * \
                (2 ** (exponent - self.EXP_BIAS))
        return -value if sign else value

    # ---------- 内部辅助函数（纯整数运算） ----------
    def _add_abs(self, other):
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        if e1 == 0 and m1 == 0:
            return LongDouble(other)
        if e2 == 0 and m2 == 0:
            return LongDouble(self)
        m1 |= (1 << self.MANT_BITS)
        m2 |= (1 << self.MANT_BITS)
        if e1 < e2:
            e1, e2 = e2, e1
            m1, m2 = m2, m1
        shift = e1 - e2
        if shift >= self.MANT_BITS + 2:
            m2 = 0
        else:
            m2 >>= shift
        result_mantissa = m1 + m2
        result_exponent = e1
        if result_mantissa >= (1 << (self.MANT_BITS + 1)):
            result_mantissa >>= 1
            result_exponent += 1
        result_mantissa &= ((1 << self.MANT_BITS) - 1)
        if result_exponent >= 0x7FFF:
            return LongDouble(float('inf'))
        result = LongDouble(0)
        result._set_bits(0, result_exponent, result_mantissa)
        return result

    def _sub_abs(self, other):
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        if e2 == 0 and m2 == 0:
            return LongDouble(self)
        m1 |= (1 << self.MANT_BITS)
        m2 |= (1 << self.MANT_BITS)
        if e1 < e2:
            e1, e2 = e2, e1
            m1, m2 = m2, m1
        shift = e1 - e2
        if shift >= self.MANT_BITS + 2:
            m2 = 0
        else:
            m2 >>= shift
        result_mantissa = m1 - m2
        result_exponent = e1
        while result_mantissa < (1 << self.MANT_BITS) and result_exponent > 0:
            result_mantissa <<= 1
            result_exponent -= 1
        result_mantissa &= ((1 << self.MANT_BITS) - 1)
        if result_exponent <= 0:
            return LongDouble(0.0)
        result = LongDouble(0)
        result._set_bits(0, result_exponent, result_mantissa)
        return result

    def _compare_abs(self, other):
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        z1 = (e1 == 0 and m1 == 0)
        z2 = (e2 == 0 and m2 == 0)
        if z1 and z2:
            return 0
        if z1:
            return -1
        if z2:
            return 1
        if e1 > e2:
            return 1
        if e1 < e2:
            return -1
        if m1 > m2:
            return 1
        if m1 < m2:
            return -1
        return 0

    # ---------- 运算符重载（80位精度） ----------
    def __add__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        if e1 == 0x7FFF or e2 == 0x7FFF:
            return LongDouble(self.to_float() + other.to_float())
        if (e1 == 0 and m1 == 0) and (e2 == 0 and m2 == 0):
            return LongDouble(-0.0 if (s1 | s2) else 0.0)
        if e1 == 0 and m1 == 0:
            return LongDouble(other)
        if e2 == 0 and m2 == 0:
            return LongDouble(self)
        if s1 == s2:
            result = self._add_abs(other)
            if s1 == 1:
                result = -result
            return result
        cmp_val = self._compare_abs(other)
        if cmp_val == 0:
            return LongDouble(0.0)
        elif cmp_val > 0:
            result = self._sub_abs(other)
            if s1 == 1:
                result = -result
            return result
        else:
            result = other._sub_abs(self)
            if s2 == 1:
                result = -result
            return result

    def __sub__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        return self + (-other)

    def __mul__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        if e1 == 0x7FFF or e2 == 0x7FFF:
            return LongDouble(self.to_float() * other.to_float())
        if (e1 == 0 and m1 == 0) or (e2 == 0 and m2 == 0):
            return LongDouble(-0.0 if (s1 ^ s2) else 0.0)
        m1 |= (1 << self.MANT_BITS)
        m2 |= (1 << self.MANT_BITS)
        prod = m1 * m2
        mantissa_high = prod >> self.MANT_BITS
        extra_shift = 0
        if mantissa_high >= (1 << (self.MANT_BITS + 1)):
            mantissa_high >>= 1
            extra_shift = 1
        result_mantissa = mantissa_high & ((1 << self.MANT_BITS) - 1)
        result_exponent = e1 + e2 - self.EXP_BIAS + extra_shift
        if result_exponent >= 0x7FFF:
            return LongDouble(float('inf') if (s1 ^ s2) == 0 else float('-inf'))
        if result_exponent <= 0:
            return LongDouble(0.0)
        result = LongDouble(0)
        result._set_bits(s1 ^ s2, result_exponent, result_mantissa)
        return result

    def __truediv__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        s1, e1, m1 = self._get_bits()
        s2, e2, m2 = other._get_bits()
        if e1 == 0x7FFF or e2 == 0x7FFF:
            return LongDouble(self.to_float() / other.to_float())
        if e1 == 0 and m1 == 0:
            if e2 == 0 and m2 == 0:
                return LongDouble(float('nan'))
            return LongDouble(-0.0 if (s1 ^ s2) else 0.0)
        if e2 == 0 and m2 == 0:
            return LongDouble(float('inf') if (s1 ^ s2) == 0 else float('-inf'))
        m1 |= (1 << self.MANT_BITS)
        m2 |= (1 << self.MANT_BITS)
        dividend = m1 << self.MANT_BITS
        quotient = dividend // m2
        remainder = dividend % m2
        shift = 0
        while quotient >= (1 << (self.MANT_BITS + 1)):
            quotient >>= 1
            shift += 1
        while quotient < (1 << self.MANT_BITS):
            quotient <<= 1
            shift -= 1
        if remainder * 2 >= m2:
            quotient += 1
            if quotient >= (1 << (self.MANT_BITS + 1)):
                quotient >>= 1
                shift += 1
        mantissa = quotient & ((1 << self.MANT_BITS) - 1)
        result_exponent = e1 - e2 + self.EXP_BIAS + shift
        if result_exponent >= 0x7FFF:
            return LongDouble(float('inf') if (s1 ^ s2) == 0 else float('-inf'))
        if result_exponent <= 0:
            return LongDouble(0.0)
        result = LongDouble(0)
        result._set_bits(s1 ^ s2, result_exponent, mantissa)
        return result

    def __neg__(self):
        result = LongDouble(self)
        result.data[9] ^= 0x80
        return result

    def __abs__(self):
        result = LongDouble(self)
        result.data[9] &= 0x7F
        return result

    # ---------- 比较运算符 ----------
    def __eq__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        return self.to_float() == other.to_float()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        if not isinstance(other, LongDouble):
            other = LongDouble(other)
        return self.to_float() < other.to_float()

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return not (self <= other)

    def __ge__(self, other):
        return not (self < other)

    # ---------- 类型转换与显示 ----------
    def __int__(self):
        return int(self.to_float())

    def __float__(self):
        return self.to_float()

    def __repr__(self):
        return f"LongDouble({self.to_float()})"

    def __str__(self):
        return str(self.to_float())

    def hex(self):
        return ' '.join(f'{b:02x}' for b in self.data)

    def is_zero(self):
        sign, exponent, mantissa = self._get_bits()
        return exponent == 0 and mantissa == 0

    def is_negative_zero(self):
        sign, exponent, mantissa = self._get_bits()
        return sign == 1 and exponent == 0 and mantissa == 0

    def is_inf(self):
        sign, exponent, mantissa = self._get_bits()
        return exponent == 0x7FFF and mantissa == 0

    def is_nan(self):
        sign, exponent, mantissa = self._get_bits()
        return exponent == 0x7FFF and mantissa != 0


# ============ 测试 ============
if __name__ == "__main__":
    print("=" * 60)
    print("测试: 字符串输入")
    print("=" * 60)
    pi = LongDouble("3.14159265358979323846")
    e = LongDouble("2.718281828459045")
    print(f"π = {pi}")
    print(f"e = {e}")
    print(f"π 的十六进制: {pi.hex()}")
    print(f"e 的十六进制: {e.hex()}")
    print(f"π + e = {pi + e}")
    print(f"π * e = {pi * e}")
    print(f"π / e = {pi / e}")

    print("\n" + "=" * 60)
    print("测试: 基本运算（从 float）")
    print("=" * 60)
    a = LongDouble(1.57)
    b = LongDouble(1.355)
    print(f"a = {a}, b = {b}")
    print(f"a + b = {a + b}")
    print(f"a - b = {a - b}")
    print(f"a * b = {a * b}")
    print(f"a / b = {a / b}")

    print("\n" + "=" * 60)
    print("测试: 负数和除法精度")
    print("=" * 60)
    c = LongDouble(-2.5)
    d = LongDouble(1.3)
    print(f"c = {c}, d = {d}")
    print(f"c + d = {c + d}")
    print(f"c - d = {c - d}")
    print(f"c * d = {c * d}")
    print(f"c / d = {c / d}")

    print("\n" + "=" * 60)
    print("测试: 1/3 和 1/7")
    print("=" * 60)
    one = LongDouble(1)
    three = LongDouble(3)
    seven = LongDouble(7)
    print(f"1 / 3 = {one / three}")
    print(f"1 / 7 = {one / seven}")
    print(f"Python float 1/3 = {1.0/3.0}")
    print(f"Python float 1/7 = {1.0/7.0}")
