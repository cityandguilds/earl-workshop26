(() => {
  const status = document.querySelector("[data-copy-status]");

  const announce = (message) => {
    if (status) status.textContent = message;
  };

  const selectValue = (element) => {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(element);
    selection.removeAllRanges();
    selection.addRange(range);
  };

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const value = target.textContent || "";
      const label = button.dataset.copyLabel || "Value";

      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(value);
          announce(`${label} copied.`);
          return;
        } catch (_error) {
          // Fall through to selecting the value when the Clipboard API is unavailable.
        }
      }
      selectValue(target);
      announce("Clipboard unavailable; value selected for copying.");
    });
  });
})();
