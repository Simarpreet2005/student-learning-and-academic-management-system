/**
 * Academic LMS — Client-Side Core Interactions
 * Pure vanilla JavaScript — Zero external tracking or proprietary dependencies.
 */

document.addEventListener('DOMContentLoaded', function () {
  // 1. Auto-dismiss flash alerts after 6 seconds (if present)
  const autoDismissAlerts = document.querySelectorAll('.alert-academic[data-auto-dismiss="true"]');
  autoDismissAlerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.4s ease';
      alert.style.opacity = '0';
      setTimeout(function () {
        alert.remove();
      }, 400);
    }, 6000);
  });

  // 2. Active Navigation link state updater
  const currentPath = window.location.pathname;
  const navLinks = document.querySelectorAll('.navbar-academic .nav-link-academic');
  navLinks.forEach(function (link) {
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });

  // 3. Simple log confirming Academic LMS script initialization
  console.log('Academic LMS core script loaded successfully. System ready.');
});
