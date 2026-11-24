const viewport = document.getElementById("viewport");
const image = document.getElementById("image");
const { userAgentData, userAgent, platform, maxTouchPoints } = navigator;
// Safari on iPad can report the same platform as a Mac.
const isMobileDevice = userAgentData?.mobile || userAgentData?.platform === "Android"
    || /Android|iPhone|iPad|iPod|Mobile/i.test(userAgent)
    || (platform === "MacIntel" && maxTouchPoints > 1);

function fitImage() {
    const { clientWidth, clientHeight } = document.documentElement;
    viewport.setAttribute("height", clientHeight);
    if (!image.naturalWidth) {
        if (image.complete) image.hidden = false;
        return;
    }

    const isMobilePortrait = isMobileDevice && clientHeight > clientWidth;
    const maxWidth = clientWidth * (isMobilePortrait ? 0.9 : 0.6);
    const maxHeight = clientHeight * 0.75;
    const scale = Math.min(1, maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
    image.width = Math.max(1, Math.floor(image.naturalWidth * scale));
    image.height = Math.max(1, Math.floor(image.naturalHeight * scale));
    image.hidden = false;
}

image.addEventListener("load", fitImage);
image.addEventListener("error", fitImage);
window.addEventListener("resize", fitImage);
fitImage();
