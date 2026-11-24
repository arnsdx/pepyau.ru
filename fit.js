const viewport = document.getElementById("viewport");
const image = document.getElementById("image");

function fitImage() {
    const { clientWidth, clientHeight } = document.documentElement;
    viewport.setAttribute("height", clientHeight);
    if (!image.naturalWidth) {
        if (image.complete) image.hidden = false;
        return;
    }

    const maxWidth = clientWidth * 0.6;
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
