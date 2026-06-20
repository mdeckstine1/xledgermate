
    (function () {
        const nativeFetch = window.fetch.bind(window);
        window.fetch = async function (...args) {
            const response = await nativeFetch(...args);
            const url = String(args[0] || '');
            if (response.status === 401 && !url.includes('/login')) {
                const next = encodeURIComponent(location.pathname + location.search);
                location.href = '/login?next=' + next;
            }
            return response;
        };
    })();
    