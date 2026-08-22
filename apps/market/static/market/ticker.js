(function () {
    const container = document.getElementById("ticker-items");
    const form = document.getElementById("ticker-add-form");
    if (!container || !form) return;

    const status = document.getElementById("ticker-status");
    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }
    const number = value => value === null || value === undefined ? "—" : Number(value).toFixed(2);

    function render(quotes) {
        container.replaceChildren();
        if (!quotes.length) {
            const empty = document.createElement("span");
            empty.className = "ticker-empty";
            empty.textContent = "Add up to 20 symbols";
            container.appendChild(empty);
            return;
        }
        quotes.forEach(quote => {
            const item = document.createElement("a");
            item.className = "ticker-item";
            item.href = "/stocks/" + encodeURIComponent(quote.symbol) + "/?market=" + quote.market;
            const changeClass = Number(quote.change) >= 0 ? "positive" : "negative";
            item.innerHTML = "<strong>" + quote.symbol + "</strong> <span>" + number(quote.price) + "</span>" +
                (quote.change_pct === null ? "" : " <span class=\"" + changeClass + "\">" + (Number(quote.change) >= 0 ? "+" : "") + number(quote.change_pct) + "%</span>");
            item.title = quote.quote_time ? "Yahoo delayed quote · " + new Date(quote.quote_time).toLocaleString() : "Quote unavailable";
            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = "×";
            remove.title = "Remove " + quote.symbol;
            remove.addEventListener("click", async event => {
                event.preventDefault(); event.stopPropagation();
                await fetch("/api/watchlist/" + quote.id + "/", {method: "DELETE", headers: {"X-CSRFToken": csrfToken()}});
                loadQuotes();
            });
            item.appendChild(remove);
            container.appendChild(item);
        });
    }

    async function loadQuotes() {
        status.textContent = "Updating…";
        try {
            const response = await fetch("/api/ticker-quotes/", {cache: "no-store"});
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Quotes unavailable");
            render(payload.quotes || []);
            const times = (payload.quotes || []).map(q => q.quote_time).filter(Boolean).sort();
            status.textContent = times.length ? "As of " + new Date(times[times.length - 1]).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "Yahoo · delayed";
        } catch (error) {
            status.textContent = error.message;
        }
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const symbolInput = document.getElementById("ticker-symbol");
        const response = await fetch("/api/watchlist/", {
            method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
            body: JSON.stringify({market: document.getElementById("ticker-market").value, symbol: symbolInput.value})
        });
        const payload = await response.json();
        if (!response.ok) { status.textContent = payload.error || "Could not add symbol"; return; }
        symbolInput.value = "";
        loadQuotes();
    });

    loadQuotes();
    window.setInterval(() => { if (!document.hidden) loadQuotes(); }, 60000);
})();
