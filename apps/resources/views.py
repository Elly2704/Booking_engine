from asgiref.sync import sync_to_async
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Avg, Count, Q
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ResourceForm
from .models import Resource, ResourceCategory


class ResourceListView(ListView):
    """Active resources with search (``?q=``) and category filter (``?category=<id>``)."""

    template_name = 'resources/resource_list.html'
    context_object_name = 'resources'
    paginate_by = 6

    def get_queryset(self):
        queryset = Resource.objects.filter(is_active=True).select_related('category')

        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

        category = self.request.GET.get('category', '')
        if category.isdigit():
            queryset = queryset.filter(category_id=category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = ResourceCategory.objects.all()
        return context


class ResourceDetailView(DetailView):
    template_name = 'resources/resource_detail.html'
    context_object_name = 'resource'

    def get_queryset(self):
        return Resource.objects.filter(is_active=True).select_related('category')


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
        if not self.object.is_active:
            return reverse('resources:resource_list')
        return reverse('resources:resource_detail', kwargs={'slug': self.object.slug})


class ResourceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Resource
    template_name = 'resources/resource_confirm_delete.html'
    permission_required = 'resources.delete_resource'
    success_url = reverse_lazy('resources:resource_list')


async def category_stats(request):
    """Number of active resources and average hourly price per category."""
    active = Q(resources__is_active=True)
    categories = [
        category
        async for category in ResourceCategory.objects.annotate(
            total_resources=Count('resources', filter=active),
            avg_price=Avg('resources__price_per_hour', filter=active),
        ).order_by('name')
    ]
    total_active = await Resource.objects.filter(is_active=True).acount()

    return await sync_to_async(render)(request, 'resources/category_stats.html', {
        'categories': categories,
        'total_active': total_active,
    })
