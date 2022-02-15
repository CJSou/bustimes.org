from django.contrib.auth import get_user_model, views as auth_views
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from . import forms

UserModel = get_user_model()


def register(request):
    if request.method == 'POST':
        form = forms.RegistrationForm(request.POST)
        if form.is_valid():
            form.save(request=request)
    else:
        form = forms.RegistrationForm()

    return render(request, 'register.html', {
        'form': form,
    })


class RegisterConfirmView(auth_views.PasswordResetConfirmView):
    pass


class LoginView(auth_views.LoginView):
    form_class = forms.LoginForm


class PasswordResetView(auth_views.PasswordResetView):
    def get_context_data(self, *args, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        context_data['form'].fields['email'].label = 'Email address'
        return context_data


def user_detail(request, pk):
    user = get_object_or_404(UserModel, pk=pk)

    revisions = user.vehiclerevision_set.select_related('vehicle', 'from_livery', 'to_livery', 'from_type', 'to_type')
    revisions = revisions.order_by('-id')
    paginator = Paginator(revisions, 100)
    page = request.GET.get('page')
    revisions = paginator.get_page(page)

    return render(request, 'user_detail.html', {
        'object': user,
        'revisions': revisions,
        # 'edits': user.edits_count(),
        # 'approved': user.approved_count(),
        # 'disapproved': user.disapproved_count(),
        # 'pending': user.pending_count()
    })
