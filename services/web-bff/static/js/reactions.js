// Shows the reaction picker popover on hover/long-press of a Like button's
// container. Pure progressive enhancement -- the plain Like button still
// works as a normal form submit with no JS at all.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".react-btn").forEach((btn) => {
    const wrapper = btn.closest("div");
    const picker = wrapper.querySelector(".reaction-picker");
    if (!picker) return;

    let hideTimer;
    const show = () => { clearTimeout(hideTimer); picker.classList.add("open"); };
    const scheduleHide = () => { hideTimer = setTimeout(() => picker.classList.remove("open"), 400); };

    wrapper.addEventListener("mouseenter", show);
    wrapper.addEventListener("mouseleave", scheduleHide);
    picker.addEventListener("mouseenter", show);
    picker.addEventListener("mouseleave", scheduleHide);
  });
});
