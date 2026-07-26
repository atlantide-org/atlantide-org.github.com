// "Copy page as Markdown": fetches the .md that scripts/llms.py writes beside
// every page and puts it on the clipboard. Delegated from document so it keeps
// working across Material's instant navigation, which swaps the page in place.
document.addEventListener("click", async (event) => {
  const button = event.target.closest(".md-copy-page");
  if (!button) return;
  const title = button.title;
  try {
    const response = await fetch(button.dataset.mdSrc);
    if (!response.ok) throw new Error(response.statusText);
    await navigator.clipboard.writeText(await response.text());
    button.title = "Copied";
    button.classList.add("md-copy-page--done");
  } catch {
    button.title = "Copy failed — use the Markdown link instead";
  }
  setTimeout(() => {
    button.title = title;
    button.classList.remove("md-copy-page--done");
  }, 2000);
});
