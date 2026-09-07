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

  document.querySelectorAll("[data-copy-target], [data-copy-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      const label = button.dataset.copyLabel || "Value";
      let value = target?.textContent || "";

      if (button.dataset.copyUrl) {
        try {
          const response = await fetch(button.dataset.copyUrl, {
            credentials: "same-origin",
            headers: { Accept: "text/plain" },
          });
          if (!response.ok) throw new Error("Credential unavailable");
          value = await response.text();
        } catch (_error) {
          announce(`${label} is temporarily unavailable.`);
          return;
        }
      }

      if (!value) return;

      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(value);
          announce(`${label} copied.`);
          return;
        } catch (_error) {
          // Fall through to selecting the value when the Clipboard API is unavailable.
        }
      }
      if (target) {
        selectValue(target);
        announce("Clipboard unavailable; value selected for copying.");
      } else {
        announce("Clipboard unavailable; use a secure browser to copy this value.");
      }
    });
  });
})();
