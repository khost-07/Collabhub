/* ============================================================
   CollabHub — Main JavaScript
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  /* ----- Sidebar Toggle (Mobile) ----- */
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  const sidebarOverlay = document.querySelector('.sidebar-overlay');

  function openSidebar() {
    if (sidebar) {
      sidebar.classList.add('open');
      if (sidebarOverlay) sidebarOverlay.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  }

  function closeSidebar() {
    if (sidebar) {
      sidebar.classList.remove('open');
      if (sidebarOverlay) sidebarOverlay.classList.remove('active');
      document.body.style.overflow = '';
    }
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function () {
      if (sidebar && sidebar.classList.contains('open')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', closeSidebar);
  }

  // Close sidebar on Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeSidebar();
    }
  });


  /* ----- Alert Auto-Dismiss ----- */
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(function () {
        alert.remove();
      }, 300);
    }, 5000);
  });


  /* ----- Alert Close Buttons ----- */
  document.addEventListener('click', function (e) {
    const closeBtn = e.target.closest('.alert-close');
    if (closeBtn) {
      const alert = closeBtn.closest('.alert');
      if (alert) {
        alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-10px)';
        setTimeout(function () {
          alert.remove();
        }, 300);
      }
    }
  });


  /* ----- Delete Confirmations ----- */
  document.addEventListener('click', function (e) {
    const target = e.target.closest('[data-confirm]');
    if (target) {
      const message = target.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
      if (!confirm(message)) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return false;
      }
    }
  });

  // For forms with data-confirm on submit buttons
  document.querySelectorAll('form').forEach(function (form) {
    const confirmBtn = form.querySelector('[data-confirm]');
    if (confirmBtn && confirmBtn.type === 'submit') {
      form.addEventListener('submit', function (e) {
        const message = confirmBtn.getAttribute('data-confirm') || 'Are you sure?';
        if (!confirm(message)) {
          e.preventDefault();
        }
      });
    }
  });


  /* ----- File Upload Validation ----- */
  const fileInputs = document.querySelectorAll('.file-input');
  const allowedExtensions = ['.pdf', '.txt'];
  const maxFileSize = 10 * 1024 * 1024; // 10 MB

  fileInputs.forEach(function (fileInput) {
    fileInput.addEventListener('change', function () {
      const form = fileInput.closest('form');
      const submitBtn = form ? form.querySelector('button[type="submit"], input[type="submit"]') : null;
      const fileNameEl = form ? form.querySelector('.file-name') : null;
      const fileErrorEl = form ? form.querySelector('.file-error') : null;

      // Clear previous messages
      if (fileNameEl) fileNameEl.textContent = '';
      if (fileErrorEl) fileErrorEl.textContent = '';
      if (submitBtn) submitBtn.disabled = false;

      if (fileInput.files.length === 0) return;

      const file = fileInput.files[0];
      const fileName = file.name;
      const fileExtension = fileName.substring(fileName.lastIndexOf('.')).toLowerCase();
      const fileSize = file.size;

      let errors = [];

      // Check extension
      if (!allowedExtensions.includes(fileExtension)) {
        errors.push('Invalid file type. Only PDF and TXT files are allowed.');
      }

      // Check size
      if (fileSize > maxFileSize) {
        errors.push('File size exceeds 10 MB limit.');
      }

      if (errors.length > 0) {
        if (fileErrorEl) {
          fileErrorEl.textContent = errors.join(' ');
        } else {
          alert(errors.join('\n'));
        }
        if (submitBtn) submitBtn.disabled = true;
        fileInput.value = '';
      } else {
        // Show selected file name
        if (fileNameEl) {
          const sizeKB = (fileSize / 1024).toFixed(1);
          const sizeStr = fileSize >= 1048576
            ? (fileSize / 1048576).toFixed(1) + ' MB'
            : sizeKB + ' KB';
          fileNameEl.textContent = fileName + ' (' + sizeStr + ')';
        }
      }
    });
  });

  // Clickable file upload area
  const uploadAreas = document.querySelectorAll('.file-upload-area');
  uploadAreas.forEach(function (area) {
    area.addEventListener('click', function () {
      const fileInput = area.closest('form').querySelector('.file-input');
      if (fileInput) fileInput.click();
    });

    // Drag & drop visual feedback
    area.addEventListener('dragover', function (e) {
      e.preventDefault();
      area.style.borderColor = 'var(--primary)';
      area.style.backgroundColor = 'var(--primary-light)';
    });

    area.addEventListener('dragleave', function () {
      area.style.borderColor = '';
      area.style.backgroundColor = '';
    });

    area.addEventListener('drop', function (e) {
      e.preventDefault();
      area.style.borderColor = '';
      area.style.backgroundColor = '';
      const fileInput = area.closest('form').querySelector('.file-input');
      if (fileInput && e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        fileInput.dispatchEvent(new Event('change'));
      }
    });
  });


  /* ----- Prevent Double Submission ----- */
  document.querySelectorAll('form:not(#chatForm):not(.no-disable)').forEach(function (form) {
    form.addEventListener('submit', function () {
      const submitBtns = form.querySelectorAll('button[type="submit"], input[type="submit"]');
      submitBtns.forEach(function (btn) {
        setTimeout(function () {
          btn.disabled = true;
          if (btn.tagName === 'BUTTON') {
            btn.dataset.originalText = btn.textContent;
            btn.textContent = 'Please wait…';
          }
        }, 10);
      });
    });
  });


  /* ----- Smooth Page Transitions ----- */
  document.querySelectorAll('a:not([target="_blank"]):not([href^="#"]):not([data-confirm])').forEach(function (link) {
    link.addEventListener('click', function (e) {
      const href = link.getAttribute('href');
      if (href && href.startsWith('/') && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        e.preventDefault();
        const main = document.querySelector('.main-content');
        if (main) {
          main.style.transition = 'opacity 0.15s ease';
          main.style.opacity = '0';
          setTimeout(function () {
            window.location.href = href;
          }, 150);
        } else {
          window.location.href = href;
        }
      }
    });
  });

});
