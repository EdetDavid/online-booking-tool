from django.urls import path

from . import views

urlpatterns = [
    path('', views.demo, name='home'),
    path('origin_airport_search/', views.origin_airport_search,
         name='origin_airport_search'),
    path('destination_airport_search/', views.destination_airport_search,
         name='destination_airport_search'),
    path('book_flight/', views.book_flight, name='book_flight'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add-flight/', views.cart_add_flight, name='cart_add_flight'),
    path('cart/add-hotel/', views.cart_add_hotel, name='cart_add_hotel'),
    path('cart/remove/<str:item_id>/', views.cart_remove, name='cart_remove'),
    path('cart/clear/', views.cart_clear, name='cart_clear'),
    path('register/', views.staff_register, name='register'),
    path('login/', views.staff_login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('administrator/profile/', views.admin_profile_view, name='admin_profile'),
    path('admin_update-profile-picture/', views.admin_update_profile_picture,
         name='admin_update_profile_picture'),
    path('update-profile-picture/', views.update_profile_picture,
         name='update_profile_picture'),
    path('administrator/register/', views.admin_register, name='admin_register'),
    path('administrator/login/', views.admin_login, name='admin_login'),
    path('administrator/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('administrator/approve_admin/',
         views.admin_approval_view, name='admin_approval_view'),

    path('administrator/approve-flight/',
         views.approve_flight, name='approve_flight'),
    path('administrator/report/', views.report, name='report'),


    path('travel-agency/register/',
         views.travel_agency_register, name='travel_agency_register'),
    path('travel-agency/login/',
         views.travel_agency_login, name='travel_agency_login'),

    path('travel-agency/organizations/',
         views.travel_agency_organizations, name='travel_agency_organizations'),
    path('travel-agency/approve_admin/',
         views.travel_agency_approval_view, name='travel_agency_approval_view'),
    path('travel-agency/approve-agency/',
         views.travel_agency_peer_approval_view, name='travel_agency_peer_approval_view'),
    path('travel-agency/report/',
         views.travel_agency_report, name='travel_agency_report'),
    path('travel-agency/approved-flights/',
         views.travel_agency_approved_flights, name='travel_agency_approved_flights'),


    path('staff-list/', views.staff_list, name='staff_list'),
    path('pending-flights/', views.pending_flights, name='pending_flights'),
    path('approved-flights/', views.approved_flights, name='approved_flights'),
    path('update-price/', views.update_price_increment,
         name='update_price_increment'),

    #     Hotel Urls


    path('hotel/', views.hotel, name='hotel'),
    path('city_search/', views.city_search, name='city_search'),
    path('book_hotel/<str:offer_id>', views.book_hotel, name='book_hotel'),
    path('rooms_per_hotel/<str:hotel>/<str:departureDate>/<str:returnDate>',
         views.rooms_per_hotel, name='rooms_per_hotel')


]

# Coming soon page for unfinished nav links
urlpatterns += [
     path('coming-soon/', views.coming_soon, name='coming_soon'),
]
