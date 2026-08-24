const scrollKey = "command-zone-scroll";

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".title small").forEach((element) => {
    element.textContent = element.textContent.replace(" · колода выбирается для каждого раунда", "");
  });
  document.querySelectorAll(".panel h3 small").forEach((element) => {
    if (element.textContent.includes("Колоду")) element.textContent = "Аккаунты создаются в разделе «Пользователи»";
  });
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
