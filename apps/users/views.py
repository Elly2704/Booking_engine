from django.views.generic import CreateView
from django.contrib.auth.views import LoginView, LogoutView
from .forms import CustomUserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from .forms import CustomUserChangeForm
from .models import User


class RegisterView(CreateView):
    """Sign-up form with optional phone and avatar; redirects to the login page."""
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')


class CustomLoginView(LoginView):
    """Login page rendered with the project template."""
    template_name = 'users/login.html'


class CustomLogoutView(LogoutView):
    """Log the user out (POST) and redirect to the resource catalogue."""
    next_page = reverse_lazy('resources:resource_list')

class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Let the logged-in user edit their own profile, including the avatar."""
    model = User
    form_class = CustomUserChangeForm
    template_name = 'users/profile.html'
    success_url = reverse_lazy('resources:resource_list')

    def get_object(self):
        return self.request.user
