(() => {
  // This path also works on HTTP pages, where navigator.clipboard is unavailable.
  const copyWithSelection = (value) => {
    const activeElement = document.activeElement;
    const selection = window.getSelection();
    const ranges = [];
    for (let i = 0; selection && i < selection.rangeCount; i += 1) {
      ranges.push(selection.getRangeAt(i).cloneRange());
    }
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.readOnly = true;
    textarea.tabIndex = -1;
    textarea.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;font-size:16px;";
    document.body.append(textarea);
    try {
      textarea.focus({ preventScroll: true });
      textarea.select();
      textarea.setSelectionRange(0, value.length);
      return document.execCommand("copy");
    } catch (_error) {
      return false;
    } finally {
      textarea.remove();
      activeElement?.focus({ preventScroll: true });
      if (selection) {
        selection.removeAllRanges();
        ranges.forEach((range) => selection.addRange(range));
      }
    }
  };

  const copyText = async (value) => {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(value);
        return true;
      } catch (_error) {
        // Some browsers expose the API but deny it; try the selection method too.
      }
    }
    return copyWithSelection(value);
  };

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
      const copied = await copyText(code.textContent);
      if (copied) {
        button.textContent = "Copied!";
        status.textContent = "Code copied.";
        resetTimer = setTimeout(() => {
          button.textContent = "Copy";
          status.textContent = "";
        }, 2000);
      } else {
        const selection = window.getSelection();
        if (selection) {
          const range = document.createRange();
          range.selectNodeContents(code);
          selection.removeAllRanges();
          selection.addRange(range);
        }
        button.textContent = "Copy";
        status.textContent = "Your browser blocked copying. Press Ctrl+C or ⌘C to copy the selected code.";
      }
    });
  });
})();
