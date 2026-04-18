chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.type !== "EXTRACT_CONTEXT") {
    return false;
  }

  const payload = {
    url: window.location.href,
    title: document.title || "",
    page_text: document.body?.innerText?.slice(0, 12000) || ""
  };

  sendResponse(payload);
  return true;
});
