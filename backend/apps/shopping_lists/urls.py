from django.urls import path

from . import views

urlpatterns = [
    path("shopping-lists/", views.ListsView.as_view(), name="shopping-lists"),
    path("shopping-lists/<uuid:list_id>/", views.ListDetailView.as_view(), name="shopping-list"),
    path(
        "shopping-lists/<uuid:list_id>/items/",
        views.ListItemsView.as_view(),
        name="shopping-list-items",
    ),
    path(
        "shopping-lists/<uuid:list_id>/items/<uuid:item_id>/",
        views.ListItemDetailView.as_view(),
        name="shopping-list-item",
    ),
]
