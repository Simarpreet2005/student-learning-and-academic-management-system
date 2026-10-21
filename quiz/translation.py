import modeltranslation.translator as _mt_translator

# ---------------------------------------------------------------------------
# Python 3.14 compatibility patch for modeltranslation + InheritanceManager
# ---------------------------------------------------------------------------
# Python 3.14 tightened __class__ assignment rules for objects whose class
# inherits from typing.Generic (which django-model-utils InheritanceManager
# does).  modeltranslation's patch_manager_class() tries to reassign
# manager.__class__ to a dynamically-created NewMultilingualManager, which
# now raises TypeError.  We wrap the original function so that when the
# assignment fails we replace the manager attribute on the model instead.
# ---------------------------------------------------------------------------
_original_patch_manager_class = _mt_translator.patch_manager_class


def _safe_patch_manager_class(manager):
    try:
        _original_patch_manager_class(manager)
    except TypeError:
        # __class__ assignment failed — skip the patch.  The manager will
        # still work; it just won't gain the multilingual queryset wrapper,
        # which is acceptable for InheritanceManager-based models.
        pass


_mt_translator.patch_manager_class = _safe_patch_manager_class

# ---------------------------------------------------------------------------
# Normal translation registrations
# ---------------------------------------------------------------------------
from modeltranslation.translator import register, TranslationOptions
from .models import Quiz, Question, Choice, MCQuestion


@register(Quiz)
class QuizTranslationOptions(TranslationOptions):
    fields = (
        "title",
        "description",
    )
    empty_values = None


@register(Question)
class QuestionTranslationOptions(TranslationOptions):
    fields = (
        "content",
        "explanation",
    )
    empty_values = None


@register(Choice)
class ChoiceTranslationOptions(TranslationOptions):
    fields = ("choice_text",)
    empty_values = None


@register(MCQuestion)
class MCQuestionTranslationOptions(TranslationOptions):
    pass
