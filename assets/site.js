(() => {
  const menus = document.querySelectorAll("details.lang-menu");
  if (!menus.length) return;

  const closeAll = (except) => {
    menus.forEach((m) => {
      if (m !== except) m.open = false;
    });
  };

  document.addEventListener("click", (e) => {
    menus.forEach((m) => {
      if (m.open && !m.contains(e.target)) m.open = false;
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
  });

  menus.forEach((m) => {
    m.addEventListener("toggle", () => {
      if (m.open) closeAll(m);
    });
  });
})();
