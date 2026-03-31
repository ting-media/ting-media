// Smooth scroll for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth' });
        }
    });
});

// Button interactions
document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', function(e) {
        this.style.transform = 'scale(0.98)';
        setTimeout(() => {
            this.style.transform = '';
        }, 100);

        const buttonText = this.textContent.trim();
        if (buttonText === 'בוא נדבר' || buttonText === 'שלחו לנו הודעה') {
            handleCTA(buttonText);
        }
    });
});

function handleCTA(buttonType) {
    console.log('CTA clicked:', buttonType);

    if (buttonType === 'בוא נדבר') {
        document.getElementById('contact').scrollIntoView({ behavior: 'smooth' });
    } else if (buttonType === 'לחצו כאן ונחזור אליכם') {
        alert('תודה! אנחנו נחזור אליכם בקרוב.');
    }
}

// Navbar transparency on scroll
window.addEventListener('scroll', function() {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.borderBottomColor = 'rgba(255, 165, 0, 0.4)';
    } else {
        navbar.style.borderBottomColor = 'rgba(255, 165, 0, 0.2)';
    }
});

// Reveal Elements on Scroll (Intersection Observer)
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const revealObserver = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            revealObserver.unobserve(entry.target);
        }
    });
}, observerOptions);

// Observe all reveal elements
document.querySelectorAll('.reveal-element, .reveal-text, .section-content').forEach(el => {
    revealObserver.observe(el);
});

// Parallax effect on scroll
window.addEventListener('scroll', function() {
    const parallaxBgs = document.querySelectorAll('.parallax-bg-light');
    const scrollPosition = window.scrollY;

    parallaxBgs.forEach(bg => {
        const parent = bg.closest('.big-text-container');
        if (parent) {
            const rect = parent.getBoundingClientRect();
            const distance = rect.top - window.innerHeight / 2;
            const movement = distance * 0.3;
            bg.style.transform = `translateY(${movement}px)`;
        }
    });
});

// Big text reveal on scroll
const bigTexts = document.querySelectorAll('.big-text');
const sectionContents = document.querySelectorAll('.big-text-section .section-content');

const textObserver = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const text = entry.target;
            text.classList.add('visible');

            // Also reveal the section content
            const section = text.closest('.big-text-container');
            if (section) {
                const content = section.querySelector('.section-content');
                if (content) {
                    content.classList.add('visible');
                }
            }

            textObserver.unobserve(entry.target);
        }
    });
}, {
    threshold: 0.3,
    rootMargin: '0px 0px -50px 0px'
});

bigTexts.forEach(text => {
    textObserver.observe(text);
});

// Stagger animation for grid items
const cards = document.querySelectorAll('.service-card, .logo-card, .video-card, .service-item');
cards.forEach((card, index) => {
    card.style.animationDelay = `${index * 0.1}s`;
});

// Mobile menu toggle (if needed in the future)
function initMobileMenu() {
    const navLinks = document.querySelector('.nav-links');
    if (window.innerWidth <= 768) {
        navLinks.style.display = 'flex';
        navLinks.style.flexDirection = 'column';
    }
}

window.addEventListener('resize', initMobileMenu);
initMobileMenu();

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Any additional initialization can go here
    console.log('TING MEDIA page loaded');
});
