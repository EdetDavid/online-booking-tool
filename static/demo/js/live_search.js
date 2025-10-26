(function(){
    function fadeOut(el){
        el.style.transition = 'opacity 300ms';
        el.style.opacity = '0.3';
    }
    function fadeIn(el){
        el.style.transition = 'opacity 300ms';
        el.style.opacity = '1';
    }

    function showOverlay(){
        let ov = document.getElementById('searchOverlay');
        if(!ov){
            ov = document.createElement('div');
            ov.id = 'searchOverlay';
            ov.innerHTML = '<div class="loader"></div>';
            document.body.appendChild(ov);
        }
        ov.classList.add('visible');
    }
    function hideOverlay(){
        const ov = document.getElementById('searchOverlay');
        if(ov) ov.classList.remove('visible');
    }

    // Intercept search forms (common patterns)
    document.addEventListener('submit', function(e){
        const form = e.target;
        // detect our search form by presence of fields used in demo: Origin, Destination, Departuredate
        if(!form.querySelector) return;
        if(form.querySelector('[name=Origin]') && form.querySelector('[name=Destination]') && form.querySelector('[name=Departuredate]')){
            e.preventDefault();
            showOverlay();
            const resultsContainer = document.querySelector('.table-responsive');
            if(resultsContainer) fadeOut(resultsContainer);

            const formData = new FormData(form);
            fetch(window.location.pathname, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            }).then(resp => {
                if(!resp.ok) throw new Error('Network response was not ok');
                return resp.text();
            }).then(html => {
                // Replace results area by finding the first .table-responsive in returned HTML
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newTable = doc.querySelector('.table-responsive');
                const newFiltersCount = doc.querySelector('#resultsCount');
                const currentTable = document.querySelector('.table-responsive');
                if(newTable && currentTable){
                    currentTable.parentNode.replaceChild(newTable, currentTable);
                }
                // Replace resultsCount if present
                if(newFiltersCount){
                    const currentCount = document.getElementById('resultsCount');
                    if(currentCount) currentCount.textContent = newFiltersCount.textContent;
                }

                // Re-init tooltips and re-run our filters initialization
                if(window.jQuery) $(document).ready(function(){ $('[data-toggle="tooltip"]').tooltip(); });
                if(window.initResultsFilters) setTimeout(window.initResultsFilters, 50);
            }).catch(err => console.error(err)).finally(()=>{
                hideOverlay();
                const resultsContainer = document.querySelector('.table-responsive');
                if(resultsContainer) fadeIn(resultsContainer);
            });
        }
    }, true);
})();
