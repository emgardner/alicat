from enum import IntEnum


class StandardNormalFlowUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    SUL_PER_MIN = 2
    SML_PER_SEC = 3
    SML_PER_MIN = 4
    SML_PER_HOUR = 5
    SL_PER_SEC = 6
    SLPM = 7
    SL_PER_HOUR = 8
    SCCS = 11
    SCCM = 12
    SCM3_PER_HOUR = 13
    SM3_PER_MIN = 14
    SM3_PER_HOUR = 15
    SM3_PER_DAY = 16
    SIN3_PER_MIN = 17
    SCFM = 18
    SCFH = 19
    KSCFM = 20
    SCFD = 21
    NUL_PER_MIN = 32
    NML_PER_SEC = 33
    NML_PER_MIN = 34
    NML_PER_HOUR = 35
    NL_PER_SEC = 36
    NLPM = 37
    NL_PER_HOUR = 38
    NCCS = 41
    NCCM = 42
    NCM3_PER_HOUR = 43
    NM3_PER_MIN = 44
    NM3_PER_HOUR = 45
    NM3_PER_DAY = 46
    COUNT = 62
    PERCENT_FULL_SCALE = 63


class TrueMassFlowUnit(IntEnum):
    MG_PER_SEC = 64
    MG_PER_MIN = 65
    G_PER_SEC = 66
    G_PER_MIN = 67
    G_PER_HOUR = 68
    KG_PER_MIN = 69
    KG_PER_HOUR = 70
    OZ_PER_SEC = 71
    OZ_PER_MIN = 72
    LB_PER_MIN = 73
    LB_PER_HOUR = 74


class TotalStandardNormalVolumeUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    SUL = 2
    SML = 3
    SL = 4
    SCM3 = 6
    SM3 = 7
    SIN3 = 8
    SFT3 = 9
    KSFT3 = 10
    NUL = 32
    NML = 33
    NL = 34
    NCM3 = 36
    NM3 = 37


class VolumetricFlowUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    UL_PER_MIN = 2
    ML_PER_SEC = 3
    ML_PER_MIN = 4
    ML_PER_HOUR = 5
    L_PER_SEC = 6
    LPM = 7
    L_PER_HOUR = 8
    US_GPM = 9
    US_GPH = 10
    CCS = 11
    CCM = 12
    CM3_PER_HOUR = 13
    M3_PER_MIN = 14
    M3_PER_HOUR = 15
    M3_PER_DAY = 16
    IN3_PER_MIN = 17
    CFM = 18
    CFH = 19
    CFD = 21
    COUNT = 62
    PERCENT_FULL_SCALE = 63


class TotalVolumeUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    UL = 2
    ML = 3
    L = 4
    US_GAL = 5
    CM3 = 6
    M3 = 7
    IN3 = 8
    FT3 = 9
    MICROPOISE = 61


class PressureUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    PA = 2
    HPA = 3
    KPA = 4
    MPA = 5
    MBAR = 6
    BAR = 7
    G_PER_CM2 = 8
    KG_PER_CM2 = 9
    PSI = 10
    PSF = 11
    MTORR = 12
    TORR = 13
    MMHG = 14
    INHG = 15
    MMH2O_4C = 16
    MMH2O_60F = 17
    CMH2O_4C = 18
    CMH2O_60F = 19
    INH2O_4C = 20
    INH2O_60F = 21
    ATM = 22
    VOLT = 61
    COUNT = 62
    PERCENT_FULL_SCALE = 63


PRESSURE_UNIT_LABELS: dict[PressureUnit, str] = {
    PressureUnit.DEFAULT: "default",
    PressureUnit.UNKNOWN: "unknown",
    PressureUnit.PA: "Pa",
    PressureUnit.HPA: "hPa",
    PressureUnit.KPA: "kPa",
    PressureUnit.MPA: "MPa",
    PressureUnit.MBAR: "mbar",
    PressureUnit.BAR: "bar",
    PressureUnit.G_PER_CM2: "g/cm2",
    PressureUnit.KG_PER_CM2: "kg/cm2",
    PressureUnit.PSI: "PSI",
    PressureUnit.PSF: "PSF",
    PressureUnit.MTORR: "mTorr",
    PressureUnit.TORR: "Torr",
    PressureUnit.MMHG: "mmHg",
    PressureUnit.INHG: "inHg",
    PressureUnit.MMH2O_4C: "mmH2O_4C",
    PressureUnit.MMH2O_60F: "mmH2O_60F",
    PressureUnit.CMH2O_4C: "cmH2O_4C",
    PressureUnit.CMH2O_60F: "cmH2O_60F",
    PressureUnit.INH2O_4C: "inH2O_4C",
    PressureUnit.INH2O_60F: "inH2O_60F",
    PressureUnit.ATM: "atm",
    PressureUnit.VOLT: "V",
    PressureUnit.COUNT: "count",
    PressureUnit.PERCENT_FULL_SCALE: "%",
}


def pressure_unit_label(
    unit: PressureUnit | int,
) -> str:
    """Return the display label for a pressure engineering-unit code."""

    pressure_unit = PressureUnit(unit)
    return PRESSURE_UNIT_LABELS[pressure_unit]


class TemperatureUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    CELSIUS = 2
    FAHRENHEIT = 3
    KELVIN = 4
    RANKINE = 5


TEMPERATURE_UNIT_LABELS: dict[TemperatureUnit, str] = {
    TemperatureUnit.DEFAULT: "default",
    TemperatureUnit.UNKNOWN: "unknown",
    TemperatureUnit.CELSIUS: "C",
    TemperatureUnit.FAHRENHEIT: "F",
    TemperatureUnit.KELVIN: "K",
    TemperatureUnit.RANKINE: "R",
}


def temperature_unit_label(unit: TemperatureUnit | int) -> str:
    """Return the display label for a temperature engineering-unit code."""

    return TEMPERATURE_UNIT_LABELS[TemperatureUnit(unit)]


class TimeIntervalUnit(IntEnum):
    DEFAULT = 0
    UNKNOWN = 1
    HMS = 2
    MILLISECOND = 3
    SECOND = 4
    MINUTE = 5
    HOUR = 6
    DAY = 7


class GasNumber(IntEnum):
    AIR = 0
    ARGON = 1
    METHANE = 2
    CARBON_MONOXIDE = 3
    CARBON_DIOXIDE = 4
    ETHANE = 5
    HYDROGEN = 6
    HELIUM = 7
    NITROGEN = 8
    NITROUS_OXIDE = 9
    NEON = 10
    OXYGEN = 11
    PROPANE = 12
    NORMAL_BUTANE = 13
    ACETYLENE = 14
    ETHYLENE = 15
    ISOBUTANE = 16
    KRYPTON = 17
    XENON = 18
    SULFUR_HEXAFLUORIDE = 19
    C25 = 20
    C10 = 21
    C8 = 22
    C2 = 23
    C75 = 24
    HE25 = 25
    HE75 = 26
    A1025 = 27
    STARGON_CS = 28
    P5 = 29
    NITRIC_OXIDE = 30
    NITROGEN_TRIFLUORIDE = 31
    AMMONIA = 32
    CHLORINE = 33
    HYDROGEN_SULFIDE = 34
    SULFUR_DIOXIDE = 35
    PROPYLENE = 36
    BUTENE_1 = 80
    CIS_2_BUTENE = 81
    ISOBUTENE = 82
    TRANS_2_BUTENE = 83
    CARBONYL_SULFIDE = 84
    DIMETHYL_ETHER = 85
    SILANE = 86
    R11 = 100
    R115 = 101
    R116 = 102
    R124 = 103
    R125 = 104
    R134A = 105
    R14 = 106
    R142B = 107
    R143A = 108
    R152A = 109
    R22 = 110
    R23 = 111
    R32 = 112
    R318 = 113
    R404A = 114
    R407C = 115
    R410A = 116
    R507A = 117
    C15 = 140
    C20 = 141
    C50 = 142
    HE50 = 143
    HE90 = 144
    BIO5M = 145
    BIO10M = 146
    BIO15M = 147
    BIO20M = 148
    BIO25M = 149
    BIO30M = 150
    BIO35M = 151
    BIO40M = 152
    BIO45M = 153
    BIO50M = 154
    BIO55M = 155
    BIO60M = 156
    BIO65M = 157
    BIO70M = 158
    BIO75M = 159
    BIO80M = 160
    BIO85M = 161
    BIO90M = 162
    BIO95M = 163
    EAN32 = 164
    EAN36 = 165
    EAN40 = 166
    HEOX20 = 167
    HEOX21 = 168
    HEOX30 = 169
    HEOX40 = 170
    HEOX50 = 171
    HEOX60 = 172
    HEOX80 = 173
    HEOX99 = 174
    EA40 = 175
    EA60 = 176
    EA80 = 177
    METABOLIC_EXHALANT = 178
    LG45 = 179
    LG6 = 180
    LG7 = 181
    LG9 = 182
    HENE9 = 183
    LG94 = 184
    SYNG1 = 185
    SYNG2 = 186
    SYNG3 = 187
    SYNG4 = 188
    NATG1 = 189
    NATG2 = 190
    NATG3 = 191
    COAL_GAS = 192
    ENDOTHERMIC_GAS = 193
    HHO = 194
    HD5 = 195
    HD10 = 196
    OCG89 = 197
    OCG93 = 198
    OCG95 = 199
    FG1 = 200
    FG2 = 201
    FG3 = 202
    FG4 = 203
    FG5 = 204
    FG6 = 205
    P10 = 206
    DEUTERIUM = 210
