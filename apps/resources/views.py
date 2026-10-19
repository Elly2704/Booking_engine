from asgiref.sync import sync_to_async
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Avg, Count, Q
from .models import Resource, ResourceCategory
from .forms import ResourceForm


class ResourceListView(ListView):
    """Public catalogue of active resources, 6 per page.

    Supports full-text-like search via ``?q=`` (name or description) and
    filtering by ``?category=<id>``.
    """
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
    """Public resource page with booking and add-to-cart actions."""
    model = Resource
    template_name = 'resources/resource_detail.html'
    context_object_name = 'resource'


class ResourceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create a resource; requires the ``resources.add_resource`` permission."""
    model = Resource
    form_class = ResourceForm
    template_name = 'resources/resource_form.html'
    permission_required = 'resources.add_resource'
    success_url = reverse_lazy('resources:resource_list')


class ResourceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit a resource; requires ``resources.change_resource``. Redirects to its detail page."""
    model = Resource
    form_class = ResourceForm
    template_name = 'resources/resource_form.html'
    permission_required = 'resources.change_resource'

    def get_success_url(self):
        return reverse_lazy('resources:resource_detail', kwargs={'slug': self.object.slug})


class ResourceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Delete a resource after confirmation; requires ``resources.delete_resource``."""
    model = Resource
    template_name = 'resources/resource_confirm_delete.html'
    permission_required = 'resources.delete_resource'
    success_url = reverse_lazy('resources:resource_list')


async def category_stats(request):
    """Async view: number of active resources and average hourly price per category."""
    categories = [
        category async for category in ResourceCategory.objects.annotate(
            total_resources=Count('resources', filter=Q(resources__is_active=True)),
            avg_price=Avg('resources__price_per_hour', filter=Q(resources__is_active=True)),
        ).order_by('name')
    ]
    total_active = await Resource.objects.filter(is_active=True).acount()
    return await sync_to_async(render)(request, 'resources/category_stats.html', {
        'categories': categories,
        'total_active': total_active,
    })
