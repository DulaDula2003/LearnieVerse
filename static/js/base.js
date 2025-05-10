// Auto-hide flash messages after 5 seconds (5000 milliseconds)
setTimeout(() => {
    const flash = document.getElementById('flashMessages');
    if (flash) {
      flash.style.display = 'none';
    }
  }, 5000);

  // Get the checkbox and the submit button
  const checkbox = document.getElementById('agreeTerms');
  const submitBtn = document.querySelector('.register-btn');
  
  // Listen for changes on the checkbox
  checkbox.addEventListener('change', () => {
    // Enable the submit button only if the checkbox is checked
    submitBtn.disabled = !checkbox.checked;
  });