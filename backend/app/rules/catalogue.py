"""Fixed action catalogue and category mappings for the Purvai rules engine."""

from typing import Literal

Category = Literal[
    "good",
    "satisfactory",
    "moderate",
    "poor",
    "very_poor",
    "severe",
]

MemberKind = Literal[
    "child_u12",
    "adult_65p",
    "heart_lung",
    "outdoor_worker",
    "adult",
]

CATEGORY_ORDER: tuple[Category, ...] = (
    "good",
    "satisfactory",
    "moderate",
    "poor",
    "very_poor",
    "severe",
)

SENSITIVE_MEMBER_KINDS: frozenset[str] = frozenset({"child_u12", "adult_65p", "heart_lung"})

ACTION_TEXTS: dict[str, str] = {
    "normal_activity": "Normal outdoor activity is fine.",
    "watch_symptoms": "Sensitive members: watch for symptoms.",
    "reduce_long_exertion": "Cut down long, hard outdoor exercise.",
    "limit_outdoor_exertion": "Sensitive members: limit long outdoor exertion.",
    "exercise_indoors": "Move exercise indoors.",
    "windows_closed_peaks": "Keep windows closed at peak hours.",
    "mostly_indoors": "Sensitive members: stay mostly indoors.",
    "mask_outdoors": "Sensitive members: wear a well-fitted mask outdoors.",
    "no_outdoor_exercise": "Avoid outdoor exercise.",
    "n95_if_out": "Wear a well-fitted N95 if you go out.",
    "stay_indoors": "Stay indoors today.",
    "purifier_on": "Run the purifier.",
    "avoid_going_out": "Avoid going out.",
    "doctor_if_symptoms": "If symptoms appear, contact a doctor.",
    "mask_and_breaks": "Outdoor work: wear a well-fitted mask and take indoor breaks.",
}

GENERAL_ACTIONS: dict[Category, tuple[str, ...]] = {
    "good": ("normal_activity",),
    "satisfactory": ("normal_activity",),
    "moderate": ("reduce_long_exertion",),
    "poor": ("exercise_indoors", "windows_closed_peaks"),
    "very_poor": ("no_outdoor_exercise", "n95_if_out"),
    "severe": ("avoid_going_out",),
}

SENSITIVE_ACTIONS: dict[Category, tuple[str, ...]] = {
    "good": ("normal_activity",),
    "satisfactory": ("normal_activity", "watch_symptoms"),
    "moderate": ("limit_outdoor_exertion",),
    "poor": ("mostly_indoors", "mask_outdoors"),
    "very_poor": ("stay_indoors", "purifier_on"),
    "severe": ("stay_indoors", "doctor_if_symptoms"),
}

OUTDOOR_WORKER_CATEGORIES: frozenset[Category] = frozenset({"poor", "very_poor", "severe"})
