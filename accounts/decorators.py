from django.shortcuts import redirect


def admin_required(
    function=None,
    redirect_to="/",
):
    """
    Decorator for views that checks that the logged-in user is a superuser.
    """
    def test_func(user):
        return bool(user.is_authenticated and user.is_active and user.is_superuser)

    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            return function(request, *args, **kwargs) if function else None
        return redirect(redirect_to)

    return wrapper if function else test_func


def lecturer_required(
    function=None,
    redirect_to="/",
):
    """
    Decorator for views that checks that the logged-in user is a lecturer or superuser.
    """
    def test_func(user):
        is_lecturer = getattr(user, "is_lecturer", False)
        return bool(user.is_authenticated and user.is_active and (is_lecturer or user.is_superuser))

    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            return function(request, *args, **kwargs) if function else None
        return redirect(redirect_to)

    return wrapper if function else test_func


def student_required(
    function=None,
    redirect_to="/",
):
    """
    Decorator for views that checks that the logged-in user is a student or superuser.
    """
    def test_func(user):
        is_student = getattr(user, "is_student", False)
        return bool(user.is_authenticated and user.is_active and (is_student or user.is_superuser))

    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            return function(request, *args, **kwargs) if function else None
        return redirect(redirect_to)

    return wrapper if function else test_func
