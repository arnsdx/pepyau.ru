const viewport = document.getElementById("viewport");
const image = document.getElementById("image");
const insetCells = document.querySelectorAll("[data-page-inset]");
const captionCells = [document.getElementById("top-caption"), document.getElementById("bottom-caption")];
const { userAgentData, userAgent, platform, maxTouchPoints } = navigator;
// Safari on iPad can report the same platform as a Mac.
const isMobileDevice = userAgentData?.mobile || userAgentData?.platform === "Android"
    || /Android|iPhone|iPad|iPod|Mobile/i.test(userAgent)
    || (platform === "MacIntel" && maxTouchPoints > 1);

function fitImage() {
    const { clientWidth, clientHeight } = document.documentElement;
    viewport.setAttribute("height", clientHeight);
    const isMobilePortrait = isMobileDevice && clientHeight > clientWidth;
    const maxWidth = clientWidth * (isMobilePortrait ? 0.9 : 0.6);
    viewport.setAttribute("width", Math.floor(maxWidth));
    // Shrink an already displayed image before measuring whether the captions wrap.
    if (!image.hidden && image.width > maxWidth) image.width = Math.max(1, Math.floor(maxWidth));

    const inset = Math.round(clientHeight * 0.05);
    for (const cell of insetCells) cell.setAttribute("height", inset);
    // Reserve the same space above and below the image to keep it centered.
    const captionHeight = Math.max(...captionCells.map(cell => cell.firstElementChild.offsetHeight));
    for (const cell of captionCells) cell.setAttribute("height", captionHeight);

    if (!image.naturalWidth) {
        if (image.complete) image.hidden = false;
        return;
    }

    const maxHeight = Math.min(clientHeight * 0.75, clientHeight - 2 * (inset + captionHeight));
    const scale = Math.min(1, maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
    image.width = Math.max(1, Math.floor(image.naturalWidth * scale));
    image.height = Math.max(1, Math.floor(image.naturalHeight * scale));
    image.hidden = false;
}

image.addEventListener("load", fitImage);
image.addEventListener("error", fitImage);
window.addEventListener("resize", fitImage);
fitImage();
