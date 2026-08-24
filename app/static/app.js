const scrollKey = "command-zone-scroll";

document.addEventListener("DOMContentLoaded", () => {
  const saved = sessionStorage.getItem(scrollKey);
  if (saved !== null) {
    sessionStorage.removeItem(scrollKey);
    requestAnimationFrame(() => window.scrollTo({ top: Number(saved), behavior: "instant" }));
  }

  document.querySelectorAll('form[action*="/winner"], form[action*="/draw"], form.deck').forEach((form) => {
    form.addEventListener("submit", () => {
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    });
  });
});
