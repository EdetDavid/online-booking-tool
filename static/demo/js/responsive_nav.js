(function () {
    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
        } else {
            callback();
        }
    }

    ready(function () {
        var sidebar = document.querySelector('.sidebar');
        var sidebarToggle = document.querySelector('.sidebar-toggle');
        var sidebarBackdrop = document.querySelector('.sidebar-backdrop');

        function setSidebar(open) {
            if (!sidebar) return;
            sidebar.classList.toggle('open', open);
            document.body.classList.toggle('sidebar-open', open);
            if (sidebarToggle) {
                sidebarToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
        }

        if (sidebar && sidebarToggle) {
            sidebarToggle.addEventListener('click', function () {
                setSidebar(!sidebar.classList.contains('open'));
            });
        }

        if (sidebarBackdrop) {
            sidebarBackdrop.addEventListener('click', function () {
                setSidebar(false);
            });
        }

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                setSidebar(false);
            }
        });

        if (sidebar) {
            sidebar.querySelectorAll('a').forEach(function (link) {
                link.addEventListener('click', function () {
                    if (window.innerWidth < 992) {
                        setSidebar(false);
                    }
                });
            });
        }

        document.querySelectorAll('.navbar-toggler[data-target]').forEach(function (toggle) {
            var targetSelector = toggle.getAttribute('data-target');
            var target = targetSelector ? document.querySelector(targetSelector) : null;
            if (!target) return;

            toggle.setAttribute('aria-expanded', target.classList.contains('show') ? 'true' : 'false');
            toggle.addEventListener('click', function () {
                window.setTimeout(function () {
                    toggle.setAttribute('aria-expanded', target.classList.contains('show') ? 'true' : 'false');
                }, 220);
            });

            target.querySelectorAll('a').forEach(function (link) {
                link.addEventListener('click', function () {
                    if (window.innerWidth < 992 && target.classList.contains('show')) {
                        if (window.jQuery && window.jQuery.fn && window.jQuery.fn.collapse) {
                            window.jQuery(target).collapse('hide');
                        } else {
                            target.classList.remove('show');
                        }
                        toggle.setAttribute('aria-expanded', 'false');
                    }
                });
            });
        });

        document.querySelectorAll('.dropdown-toggle').forEach(function (dropdownToggle) {
            dropdownToggle.addEventListener('click', function () {
                var dropdown = dropdownToggle.parentElement;
                if (dropdown && dropdown.classList.contains('dropdown')) {
                    dropdown.classList.toggle('active');
                }
            });
        });
    });
}());
