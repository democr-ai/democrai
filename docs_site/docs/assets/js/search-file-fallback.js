(function () {
  if (window.location.protocol !== "file:") {
    return;
  }

  window.Worker = undefined;

  function joinUrl(base, path) {
    if (path.substring(0, 1) === "/") {
      return path;
    }
    if (base.substring(base.length - 1) === "/") {
      return base + path;
    }
    return base + "/" + path;
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function formatResult(location, title, summary) {
    const href = joinUrl(base_url, location);
    return '<article><h3><a href="' + href + '">' + title + "</a></h3><p>" + summary + "</p></article>";
  }

  function displayResults(results) {
    const container = document.getElementById("mkdocs-search-results");
    if (!container) {
      return;
    }
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    if (!results.length) {
      container.insertAdjacentHTML("beforeend", "<p>No results found</p>");
      return;
    }
    results.forEach((result) => {
      container.insertAdjacentHTML(
        "beforeend",
        formatResult(result.location, result.title, result.text.substring(0, 200)),
      );
    });
  }

  function buildIndex(searchData) {
    const documents = {};
    const index = lunr(function () {
      this.field("title");
      this.field("text");
      this.ref("location");
      searchData.docs.forEach((doc) => {
        this.add(doc);
        documents[doc.location] = doc;
      });
    });
    return { index, documents, minSearchLength: (searchData.config?.min_search_length || 3) - 1 };
  }

  async function initFileSearch() {
    await loadScript(joinUrl(base_url, "search/lunr.js"));
    await loadScript(joinUrl(base_url, "search/search_index.js"));

    const searchData = window.__MKDOCS_SEARCH_DATA__;
    if (!searchData || !window.lunr) {
      return;
    }

    const state = buildIndex(searchData);
    const input = document.getElementById("mkdocs-search-query");
    if (!input) {
      return;
    }

    window.min_search_length = state.minSearchLength;
    window.doSearch = function () {
      const query = input.value;
      if (query.length <= state.minSearchLength) {
        displayResults([]);
        return;
      }
      const results = state.index.search(query).map((result) => state.documents[result.ref]);
      displayResults(results);
    };

    input.addEventListener("keyup", window.doSearch);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initFileSearch().catch((error) => {
      console.error("File search fallback failed", error);
    });
  });
})();
