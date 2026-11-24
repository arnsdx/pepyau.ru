const viewport = document.getElementById("viewport");
const image = document.getElementById("image");

function fitImage() {
    const { clientWidth, clientHeight } = document.documentElement;
    viewport.setAttribute("height", clientHeight);
    if (!image.naturalWidth) return;

    const scale = Math.min(1, clientWidth / image.naturalWidth, clientHeight / image.naturalHeight);
    image.width = Math.max(1, Math.floor(image.naturalWidth * scale));
    image.height = Math.max(1, Math.floor(image.naturalHeight * scale));
}

image.addEventListener("load", fitImage);
window.addEventListener("resize", fitImage);
fitImage();
