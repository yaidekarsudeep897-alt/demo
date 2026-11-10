// SmartGram Core Frontend Helpers

document.addEventListener("DOMContentLoaded", function() {
  // Auto dismiss flash alerts after 6 seconds
  setTimeout(function() {
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach(function(alert) {
      alert.style.transition = "opacity 0.5s ease";
      alert.style.opacity = "0";
      setTimeout(() => alert.remove(), 500);
    });
  }, 6000);

  // Star Rating Interaction
  initStarRatings();
  initNavigationMenu();
  initPanchayatSearch();
});

function initNavigationMenu() {
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.querySelector("#main-navigation");
  if (!toggle || !navigation) return;

  toggle.addEventListener("click", function() {
    const isOpen = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Open navigation menu" : "Close navigation menu");
    navigation.classList.toggle("is-open", !isOpen);
  });

  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation menu");
      navigation.classList.remove("is-open");
      toggle.focus();
    }
  });
}

function initPanchayatSearch() {
  document.querySelectorAll("select[name='panchayat_id']").forEach(select => {
    if (select.options.length < 100 || select.dataset.searchReady) return;
    select.dataset.searchReady = "true";

    const search = document.createElement("input");
    search.type = "search";
    search.className = "form-control panchayat-search";
    search.placeholder = "Search by Panchayat, district or LGD code";
    search.setAttribute("aria-label", "Search Gram Panchayats");
    select.parentNode.insertBefore(search, select);

    search.addEventListener("input", function() {
      const query = search.value.trim().toLocaleLowerCase();
      Array.from(select.options).forEach(option => {
        option.hidden = Boolean(query) && !option.textContent.toLocaleLowerCase().includes(query);
      });
      if (select.selectedOptions.length && select.selectedOptions[0].hidden) {
        select.value = "";
      }
    });
  });
}

function initStarRatings() {
  const ratingContainers = document.querySelectorAll(".interactive-rating");
  ratingContainers.forEach(container => {
    const stars = container.querySelectorAll(".star");
    const input = container.querySelector("input[type='hidden']");

    stars.forEach(star => {
      star.addEventListener("click", function() {
        const val = this.getAttribute("data-value");
        if (input) input.value = val;
        updateStarsDisplay(stars, val);
      });

      star.addEventListener("mouseenter", function() {
        const val = this.getAttribute("data-value");
        updateStarsDisplay(stars, val);
      });
    });

    container.addEventListener("mouseleave", function() {
      const currentVal = input ? input.value : 0;
      updateStarsDisplay(stars, currentVal);
    });
  });
}

function updateStarsDisplay(stars, value) {
  stars.forEach(star => {
    const starVal = parseInt(star.getAttribute("data-value"));
    if (starVal <= value) {
      star.classList.add("active");
      star.innerHTML = "★";
    } else {
      star.classList.remove("active");
      star.innerHTML = "☆";
    }
  });
}
