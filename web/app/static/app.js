document.querySelectorAll("[data-open]").forEach(function (el) {
  el.addEventListener("click", function () {
    var id = el.getAttribute("data-open");
    var dialog = document.getElementById(id);
    if (dialog && dialog.showModal) dialog.showModal();
  });
});

document.querySelectorAll("[data-close]").forEach(function (el) {
  el.addEventListener("click", function () {
    var dialog = el.closest("dialog");
    if (dialog) dialog.close();
  });
});
