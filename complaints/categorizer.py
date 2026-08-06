"""
Rule-based complaint categoriser (bonus feature; SRS section 3.1 "Categorization
Errors" mitigation).

Deliberately keyword-driven rather than model-driven: it needs no training data,
no paid API and no extra dependency, and its suggestions are always advisory -
the student and the HOD can override them.
"""

from collections import defaultdict

from .models import ComplaintCategory

#: keyword -> (category, weight). Longer, more specific phrases score higher.
KEYWORD_RULES = {
    ComplaintCategory.ACADEMIC: {
        "exam": 3,
        "examination": 3,
        "paper": 2,
        "marks": 3,
        "grade": 3,
        "grading": 3,
        "result": 3,
        "transcript": 3,
        "attendance": 3,
        "lecture": 2,
        "class": 2,
        "teacher": 2,
        "professor": 2,
        "syllabus": 3,
        "course": 2,
        "assignment": 3,
        "quiz": 3,
        "lab": 2,
        "timetable": 3,
        "semester": 2,
        "cgpa": 3,
    },
    ComplaintCategory.HOSTEL: {
        "hostel": 4,
        "dorm": 3,
        "dormitory": 3,
        "room": 2,
        "roommate": 3,
        "mess": 3,
        "canteen": 3,
        "food": 2,
        "warden": 4,
        "water": 2,
        "electricity": 2,
        "fan": 2,
        "washroom": 3,
        "bathroom": 3,
        "laundry": 2,
        "accommodation": 3,
        "bed": 2,
    },
    ComplaintCategory.ADMINISTRATION: {
        "fee": 3,
        "fees": 3,
        "challan": 3,
        "admission": 3,
        "enrollment": 3,
        "enrolment": 3,
        "registration": 3,
        "office": 2,
        "clerk": 3,
        "staff": 2,
        "certificate": 3,
        "document": 2,
        "id card": 3,
        "library": 3,
        "scholarship": 3,
        "refund": 3,
        "harassment": 3,
        "security": 2,
        "parking": 2,
        "transport": 3,
        "bus": 2,
        "cleanliness": 2,
    },
}


def suggest_category(text):
    """
    Return ``(category_value, confidence)`` for the supplied free text.

    ``confidence`` is a 0-1 float; anything below 0.2 is reported as ``OTHER``
    so the UI never pushes a weak guess.
    """
    if not text:
        return ComplaintCategory.OTHER.value, 0.0

    haystack = f" {text.lower()} "
    scores = defaultdict(int)
    for category, keywords in KEYWORD_RULES.items():
        for keyword, weight in keywords.items():
            if f" {keyword} " in haystack or f" {keyword}s " in haystack:
                scores[category] += weight

    if not scores:
        return ComplaintCategory.OTHER.value, 0.0

    total = sum(scores.values())
    best = max(scores.items(), key=lambda item: item[1])
    confidence = round(best[1] / total, 2) if total else 0.0
    if best[1] < 3:
        return ComplaintCategory.OTHER.value, 0.0
    return best[0].value if hasattr(best[0], "value") else str(best[0]), confidence


def suggest_department(text, departments):
    """
    Suggest a department by matching its name/code against the complaint text.

    ``departments`` is any iterable of :class:`accounts.models.Department`.
    Returns the best match or ``None``.
    """
    if not text:
        return None
    haystack = text.lower()
    best, best_score = None, 0
    for department in departments:
        score = 0
        name = (department.name or "").lower()
        code = (department.code or "").lower()
        if name and name in haystack:
            score += len(name)
        for word in name.split():
            if len(word) > 3 and word in haystack:
                score += len(word)
        if code and f" {code} " in f" {haystack} ":
            score += len(code) + 2
        if score > best_score:
            best, best_score = department, score
    return best if best_score >= 4 else None
