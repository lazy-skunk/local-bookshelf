const searchForm = document.querySelector("#book-search");
const queryInput = searchForm.elements.namedItem("query");
const searchMode = searchForm.elements.namedItem("search_mode");
const results = document.querySelector("#search-results");
const searchStatus = document.querySelector("#search-status");

let searchTimer;
let activeRequest;
let isComposing = false;

function cancelSearch() {
  clearTimeout(searchTimer);
  activeRequest?.abort();
  searchStatus.hidden = true;
  searchStatus.textContent = "";
  results.removeAttribute("aria-busy");
}

async function search() {
  cancelSearch();
  const requestController = new AbortController();
  activeRequest = requestController;
  const url = new URL(searchForm.action);
  url.search = new URLSearchParams(new FormData(searchForm));

  searchStatus.textContent = "検索中…";
  searchStatus.hidden = false;
  results.setAttribute("aria-busy", "true");

  try {
    const response = await fetch(url, { signal: requestController.signal });
    const responseDocument = new DOMParser().parseFromString(
      await response.text(),
      "text/html",
    );
    if (requestController.signal.aborted) return;

    const updatedResults = responseDocument.querySelector("#search-results");
    if (!updatedResults || (!response.ok && response.status !== 503)) {
      throw new Error("Search results unavailable");
    }

    results.replaceChildren(...updatedResults.childNodes);
    if (response.ok) history.replaceState(history.state, "", url);
    searchStatus.hidden = true;
    searchStatus.textContent = "";
  } catch {
    if (!requestController.signal.aborted) {
      searchStatus.textContent = "検索に失敗しました。もう一度お試しください。";
    }
  } finally {
    if (activeRequest === requestController) {
      activeRequest = undefined;
      results.removeAttribute("aria-busy");
    }
  }
}

function scheduleSearch() {
  cancelSearch();
  if (!isComposing) searchTimer = setTimeout(search, 500);
}

queryInput.addEventListener("compositionstart", () => {
  isComposing = true;
  cancelSearch();
});
queryInput.addEventListener("compositionend", () => {
  isComposing = false;
  scheduleSearch();
});
queryInput.addEventListener("input", scheduleSearch);
searchMode.addEventListener("change", scheduleSearch);
searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!isComposing) search();
});
