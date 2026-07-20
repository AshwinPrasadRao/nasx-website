// NASx generic carousel — wires prev/next buttons to any .nasx-carousel block.
// Each block: .nasx-carousel > (.nasx-track with .nc-card children) + .nc-nav > .nc-prev/.nc-next
(function () {
  function initCarousel(root) {
    var track = root.querySelector('.nasx-track');
    var prev = root.querySelector('.nc-prev');
    var next = root.querySelector('.nc-next');
    if (!track || !prev || !next) return;

    function scrollAmount() {
      if (window.innerWidth < 768) return track.offsetWidth;        // one card-ish
      if (window.innerWidth < 1200) return track.offsetWidth / 2;
      return track.offsetWidth / 3;
    }

    function updateState() {
      var atStart = track.scrollLeft <= 10;
      var atEnd = track.scrollWidth - track.clientWidth - track.scrollLeft <= 10;
      prev.disabled = atStart;
      next.disabled = atEnd;
    }

    prev.addEventListener('click', function () {
      track.scrollBy({ left: -scrollAmount(), behavior: 'smooth' });
    });
    next.addEventListener('click', function () {
      track.scrollBy({ left: scrollAmount(), behavior: 'smooth' });
    });
    track.addEventListener('scroll', updateState);
    window.addEventListener('resize', updateState);
    updateState();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.nasx-carousel').forEach(initCarousel);
  });
})();
