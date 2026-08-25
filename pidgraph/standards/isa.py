"""ISA-5.1 identification vocabulary.

Seeded from the project's normative reference (see ``docs/reference/``), which reproduces the
five-column letter table, with the additions the current standard makes overlaid as an explicit,
labelled delta.

**Three editions are in play and the schema names which one it claims.** The reference guide's
letter table is the 1984 table despite its cover citing 2009 -- it carries the ``M`` = *Momentary*
modifier that 2009 deleted, gives ``P`` as *Pressure, Vacuum* rather than *Pressure*, and has no
Safety Instrumented System entry at all. Taking it wholesale would leave the parser with no concept
of SIS tagging, which is a safety-relevant blind spot, so the 2009 additions are overlaid and each
row records where it came from.

See ``docs/assumptions.md`` STD-01, STD-02, STD-07, STD-08, STD-09, DESIGN-08.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Edition(StrEnum):
    ISA_1984 = "ANSI/ISA-5.1-1984"
    ISA_2009 = "ANSI/ISA-5.1-2009"
    GUIDE = "reference-guide"


class Column(StrEnum):
    """Position in the identification table. Letters must appear in column order."""

    VARIABLE = "measured_or_initiating_variable"
    VARIABLE_MODIFIER = "variable_modifier"
    READOUT = "readout_or_passive_function"
    OUTPUT = "output_function"
    FUNCTION_MODIFIER = "function_modifier"


@dataclass(frozen=True)
class LetterMeaning:
    letter: str
    column: Column
    meaning: str
    edition: Edition
    users_choice: bool = False
    note: str = ""


# --- Column 1: measured or initiating variable ------------------------------------------------
VARIABLES: tuple[LetterMeaning, ...] = tuple(
    LetterMeaning(letter, Column.VARIABLE, meaning, Edition.GUIDE, users_choice=uc)
    for letter, meaning, uc in [
        ("A", "Analysis", False),
        ("B", "Burner, Combustion", False),
        ("C", "User's Choice", True),
        ("D", "User's Choice", True),
        ("E", "Voltage", False),
        ("F", "Flow Rate", False),
        ("G", "User's Choice", True),
        ("H", "Hand", False),
        ("I", "Current (Electrical)", False),
        ("J", "Power", False),
        ("K", "Time, Time Schedule", False),
        ("L", "Level", False),
        ("M", "User's Choice", True),
        ("N", "User's Choice", True),
        ("O", "User's Choice", True),
        ("P", "Pressure, Vacuum", False),
        ("Q", "Quantity", False),
        ("R", "Radiation", False),
        ("S", "Speed, Frequency", False),
        ("T", "Temperature", False),
        ("U", "Multivariable", False),
        ("V", "Vibration, Mechanical Analysis", False),
        ("W", "Weight, Force", False),
        ("X", "Unclassified", False),
        ("Y", "Event, State or Presence", False),
        ("Z", "Position, Dimension", False),
    ]
)

# --- Column 2: variable modifier ---------------------------------------------------------------
VARIABLE_MODIFIERS: tuple[LetterMeaning, ...] = (
    LetterMeaning("D", Column.VARIABLE_MODIFIER, "Differential", Edition.GUIDE),
    LetterMeaning("F", Column.VARIABLE_MODIFIER, "Ratio (Fraction)", Edition.GUIDE),
    LetterMeaning("J", Column.VARIABLE_MODIFIER, "Scan", Edition.GUIDE),
    LetterMeaning("K", Column.VARIABLE_MODIFIER, "Time Rate of Change", Edition.GUIDE),
    LetterMeaning(
        "M", Column.VARIABLE_MODIFIER, "Momentary", Edition.ISA_1984,
        note="deleted in the 2009 edition; retained because the reference guide lists it",
    ),
    LetterMeaning("Q", Column.VARIABLE_MODIFIER, "Integrate, Totalize", Edition.GUIDE),
    LetterMeaning("S", Column.VARIABLE_MODIFIER, "Safety", Edition.GUIDE),
    LetterMeaning("X", Column.VARIABLE_MODIFIER, "X Axis", Edition.GUIDE),
    LetterMeaning("Y", Column.VARIABLE_MODIFIER, "Y Axis", Edition.GUIDE),
    LetterMeaning(
        "Z", Column.VARIABLE_MODIFIER, "Safety Instrumented System", Edition.ISA_2009,
        note="ADDED from the 2009 edition. The reference guide's table predates it, so without "
             "this overlay a safety-instrumented loop is classified as an ordinary position loop",
    ),
)

# --- Column 3: readout or passive function -----------------------------------------------------
READOUTS: tuple[LetterMeaning, ...] = tuple(
    LetterMeaning(letter, Column.READOUT, meaning, Edition.GUIDE)
    for letter, meaning in [
        ("A", "Alarm"), ("B", "User's Choice"), ("E", "Sensor (Primary Element)"),
        ("G", "Glass, Viewing Device"), ("I", "Indicate"), ("L", "Light"),
        ("N", "User's Choice"), ("O", "Orifice, Restriction"), ("P", "Point (Test) Connection"),
        ("Q", "Integrate, Totalize"), ("R", "Record"), ("U", "Multifunction"),
        ("W", "Well"), ("X", "Unclassified"),
    ]
)

# --- Column 4: output function -----------------------------------------------------------------
OUTPUTS: tuple[LetterMeaning, ...] = tuple(
    LetterMeaning(letter, Column.OUTPUT, meaning, Edition.GUIDE)
    for letter, meaning in [
        ("B", "User's Choice"), ("C", "Control"), ("K", "Control Station"),
        ("N", "User's Choice"), ("S", "Switch"), ("T", "Transmit"),
        ("U", "Multifunction"), ("V", "Valve, Damper, Louver"), ("X", "Unclassified"),
        ("Y", "Relay, Compute, Convert"),
        ("Z", "Driver, Actuator, Unclassified Final Control Element"),
    ]
)

# --- Column 5: function modifier ---------------------------------------------------------------
FUNCTION_MODIFIERS: tuple[LetterMeaning, ...] = tuple(
    LetterMeaning(code, Column.FUNCTION_MODIFIER, meaning, Edition.GUIDE)
    for code, meaning in [
        ("HH", "High-High"), ("LL", "Low-Low"), ("H", "High"), ("L", "Low"),
        ("M", "Middle, Intermediate"), ("U", "Multifunction"), ("X", "Unclassified"),
    ]
)

# --- Safety semantics --------------------------------------------------------------------------

SAFETY_DEVICES: frozenset[str] = frozenset({"FSV", "PSV", "TSV", "PSE", "TSE"})
"""Tags where ``S`` means *Safety* rather than *Switch*.

The gate is on the **first letter** (F, P or T) *and* the device being a self-actuated
emergency-protective element -- not on the trailing letters. An earlier formulation gated on the
remaining letters being V or E, which would classify ``LSV``, ``ASE`` and ``ZSV`` as safety
devices. See docs/assumptions.md STD-01.
"""

SIS_MODIFIER = "Z"
"""``Z``, not ``S``, denotes a Safety Instrumented System (2009 note 30)."""

# --- Failure positions ---------------------------------------------------------------------------

FAILURE_POSITIONS: dict[str, str] = {
    "FO": "Fail open",
    "FC": "Fail closed",
    "FL": "Fail locked in last position",
    "FL/DO": "Fail last position, drift open",
    "FL/DC": "Fail last position, drift closed",
}
"""Exactly five codes. ``FI`` is **not** among them -- in the reference guide ``FI`` is
*Flow Indicator*. See docs/assumptions.md STD-08."""

AMBIGUOUS_ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "FC": ("Flow Controller", "Fail Closed"),
}
"""Codes the reference guide defines more than once. Resolution is positional: inside a bubble the
code is a loop function, adjacent to a final control element it is a failure position. A single
meaning per code would merge two different kinds of object."""

# --- Bubble geometry -----------------------------------------------------------------------------


@dataclass(frozen=True)
class BubbleSemantics:
    """What a device circle's decoration means.

    Three independent predicates rather than one enum, because cross-reference rules about
    operator action during a procedure depend on *accessibility*, not on the drafting symbol.
    """

    line_style: str
    location: str
    visible: bool
    operator_accessible: bool


BUBBLE_LOCATIONS: dict[str, BubbleSemantics] = {
    "none": BubbleSemantics("none", "field, not panel or cabinet mounted", True, True),
    "single_solid": BubbleSemantics(
        "single_solid", "front of central or main panel or console", True, True
    ),
    "single_dashed": BubbleSemantics(
        "single_dashed", "rear of central or main panel, or cabinet behind panel", False, False
    ),
    "double_solid": BubbleSemantics(
        "double_solid", "front of secondary or local panel or console", True, True
    ),
    "double_dashed": BubbleSemantics(
        "double_dashed", "rear of secondary or local panel, or field cabinet", False, False
    ),
}

AMBIGUOUS_SHAPES: dict[str, tuple[str, ...]] = {
    "diamond_in_square": (
        "shared display/shared control, alternate choice",
        "safety instrumented system",
        "programmable logic control (pre-2009 drawings only)",
    ),
}
"""Shapes that cannot be resolved from geometry alone.

The standard's own table heads the column "Alternate Choice **or** Safety Instrumented System", so
the shape does not distinguish them -- that depends on the drawing's legend sheet. Assigning one
class here would be wrong on a large fraction of real drawings, so the ambiguity is emitted and a
``requires_legend`` flag is set. See docs/assumptions.md STD-09.
"""


def lookup(letters: tuple[LetterMeaning, ...], letter: str) -> LetterMeaning | None:
    return next((m for m in letters if m.letter == letter), None)


def is_safety_device(function: str) -> bool:
    return function.upper() in SAFETY_DEVICES


def is_sis(variable_modifier: str | None) -> bool:
    return (variable_modifier or "").upper() == SIS_MODIFIER
