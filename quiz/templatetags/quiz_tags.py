from django import template

register = template.Library()


@register.inclusion_tag("quiz/correct_answer.html", takes_context=True)
def correct_answer_for_all(context, question):
    """
    processes the correct answer based on a given question object
    if the answer is incorrect, informs the user
    """
    answers = question.get_choices()
    incorrect_list = context.get("incorrect_questions", [])
    user_was_incorrect = question.id in incorrect_list

    return {"previous": {"answers": answers}, "user_was_incorrect": user_was_incorrect}


@register.filter
def answer_choice_to_string(question, answer):
    return question.answer_choice_to_string(answer)
