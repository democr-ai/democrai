window.onSearchBarClick = (event) => {
  const bottomSidebar = document.getElementById("bottom-sidebar");
  if (bottomSidebar && bottomSidebar.open) {
    bottomSidebar.close();
  }

  const menuButton = document.getElementById("menu-button");
  if (menuButton) {
    menuButton.dataset.state = "closed";
  }

  const dialog = document.getElementById("search-dialog");
  if (!dialog) {
    return;
  }

  if (!dialog.open) {
    dialog.showModal();
  }

  requestAnimationFrame(() => {
    const input = dialog.querySelector("input");
    if (input) {
      input.focus();
      input.select?.();
    }
  });
};
