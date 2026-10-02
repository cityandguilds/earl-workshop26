(() => {
  document.querySelectorAll(".markdown-body pre").forEach((pre, index) => {
    const code = pre.querySelector("code");
    if (!code) return;

    const block = document.createElement("div");
    block.className = "code-block";
    const toolbar = document.createElement("div");
    toolbar.className = "code-toolbar";
    const status = document.createElement("span");
    status.className = "code-copy-status";
    status.setAttribute("role", "status");
    const button = document.createElement("button");
    button.className = "copy-button";
    button.type = "button";
    button.textContent = "Copy";
    button.setAttribute("aria-label", `Copy code block ${index + 1}`);
    toolbar.append(status, button);
    pre.before(block);
    block.append(toolbar, pre);
    pre.tabIndex = 0;
    pre.setAttribute("aria-label", `Code block ${index + 1}`);

    let resetTimer;
    button.addEventListener("click", async () => {
      clearTimeout(resetTimer);
      status.textContent = "";
      button.disabled = true;
      try {
        if (!navigator.clipboard || !window.isSecureContext) {
          throw new Error("Clipboard unavailable");
        }
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = "Copied!";
        status.textContent = "Code copied.";
        resetTimer = setTimeout(() => {
          button.textContent = "Copy";
          status.textContent = "";
        }, 2000);
      } catch (_error) {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
        button.textContent = "Copy";
        status.textContent = "Clipboard unavailable; code selected for manual copying.";
      } finally {
        button.disabled = false;
      }
    });
  });
})();
