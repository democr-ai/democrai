document.querySelectorAll("[data-code-group]").forEach((group) => {
  const tabs = Array.from(group.querySelectorAll("[data-code-group-tab]"));
  const panels = Array.from(group.querySelectorAll("[data-code-group-panel]"));

  function activate(targetId) {
    tabs.forEach((tab) => {
      const isActive = tab.getAttribute("data-target") === targetId;
      tab.dataset.active = isActive ? "true" : "false";
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.setAttribute("tabindex", isActive ? "0" : "-1");
    });

    panels.forEach((panel) => {
      const isActive = panel.id === targetId;
      panel.hidden = !isActive;
      panel.dataset.active = isActive ? "true" : "false";
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      activate(tab.getAttribute("data-target"));
    });
  });

  const initial = tabs.find((tab) => tab.dataset.active === "true") || tabs[0];
  if (initial) {
    activate(initial.getAttribute("data-target"));
  }
});
