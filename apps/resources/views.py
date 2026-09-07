from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from .models import Resource
from .forms import ResourceForm


class ResourceListView(ListView):
    model = Resource
    template_name = 'resources/resource_list.html'
    context_object_name = 'resources'
    paginate_by = 6

    def get_queryset(self):
        queryset = Resource.objects.filter(is_active=True)
        query = self.request.GET.get('q')
        category = self.request.GET.get('category')
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset


class ResourceDetailView(DetailView):
    model = Resource
    template_name = 'resources/resource_detail.html'
    context_object_name = 'resource'


class ResourceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Resource
    form_class = ResourceForm
    template_name = 'resources/resource_form.html'
    permission_required = 'resources.add_resource'
    success_url = reverse_lazy('resources:resource_list')


class ResourceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Resource
    form_class = ResourceForm
    template_name = 'resources/resource_form.html'
    permission_required = 'resources.change_resource'

    def get_success_url(self):
        return reverse_lazy('resources:resource_detail', kwargs={'slug': self.object.slug})


class ResourceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Resource
    template_name = 'resources/resource_confirm_delete.html'
    permission_required = 'resources.delete_resource'
    success_url = reverse_lazy('resources:resource_list')