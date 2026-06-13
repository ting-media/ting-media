/**
 * Dynamic content loader for TING MEDIA landing page
 * Fetches portfolio, carousel, and content from CMS API
 */

const API_BASE = window.location.origin;

// Load all dynamic content on page load
document.addEventListener('DOMContentLoaded', function() {
    loadHeroContent();
    loadPortfolios();
    loadCarousel();
    loadContentSections();
});

/**
 * Load hero section content from CMS
 */
async function loadHeroContent() {
    try {
        const response = await fetch(`${API_BASE}/api/cms/content/hero`);
        const data = await response.json();

        if (data.success && data.content) {
            const content = data.content;
            if (content.title) {
                document.getElementById('heroTitle').textContent = content.title;
            }
            if (content.subtitle) {
                document.getElementById('heroSubtitle').textContent = content.subtitle;
            }
        }
    } catch (e) {
        console.warn('Could not load hero content from CMS:', e);
    }
}

/**
 * Load and render portfolio grid from CMS
 */
async function loadPortfolios() {
    try {
        const response = await fetch(`${API_BASE}/api/cms/portfolios`);
        const data = await response.json();

        if (data.success && data.portfolios && data.portfolios.length > 0) {
            const portfolioSection = document.querySelector('[id*="portfolio"]');
            if (!portfolioSection) return;

            // Find or create portfolio grid
            let grid = portfolioSection.querySelector('.video-grid');
            if (!grid) {
                grid = document.createElement('div');
                grid.className = 'video-grid';
                grid.setAttribute('role', 'grid');
                portfolioSection.appendChild(grid);
            }

            // Render portfolio items
            const html = data.portfolios.slice(0, 12).map(p => `
                <div class="video-card reveal-element" role="gridcell">
                    <div class="video-container" onclick="openVideoModal('${p.video_url.replace(/'/g, "\\'")}')">
                        ${p.thumbnail_url ?
                            `<img src="${p.thumbnail_url}" alt="${p.title}" class="video-thumbnail">` :
                            `<div class="video-placeholder" style="background: linear-gradient(135deg, #FFA500, #FF8C00); display: flex; align-items: center; justify-content: center; height: 200px; border-radius: 8px;">
                                <span style="color: white; font-size: 48px;">🎬</span>
                            </div>`
                        }
                        <div class="play-button">▶</div>
                    </div>
                    <h3 class="video-title">${p.title}</h3>
                    <p class="video-category">${p.category}</p>
                    ${p.description ? `<p class="video-description">${p.description}</p>` : ''}
                </div>
            `).join('');

            grid.innerHTML = html;
        }
    } catch (e) {
        console.warn('Could not load portfolios from CMS:', e);
    }
}

/**
 * Load and render carousel from CMS
 */
async function loadCarousel() {
    try {
        const response = await fetch(`${API_BASE}/api/cms/carousel`);
        const data = await response.json();

        if (data.success && data.carousel && data.carousel.length > 0) {
            // Create carousel HTML if it doesn't exist
            const carouselSection = document.querySelector('.carousel-section');
            if (!carouselSection) return;

            const html = `
                <div class="carousel-container">
                    <div class="carousel-track">
                        ${data.carousel.map((item, idx) => `
                            <div class="carousel-item" style="display: ${idx === 0 ? 'flex' : 'none'};">
                                ${item.video_url ?
                                    `<video src="${item.video_url}" style="width: 100%; height: 300px; object-fit: cover; border-radius: 12px;" muted autoplay loop></video>` :
                                    item.image_url ?
                                    `<img src="${item.image_url}" style="width: 100%; height: 300px; object-fit: cover; border-radius: 12px;" alt="${item.title}">` :
                                    `<div style="width: 100%; height: 300px; background: rgba(255, 165, 0, 0.1); border-radius: 12px;"></div>`
                                }
                                <h3>${item.title}</h3>
                                ${item.description ? `<p>${item.description}</p>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;

            const container = carouselSection.querySelector('.carousel-container') ||
                            document.createElement('div');
            container.innerHTML = html;
            if (!carouselSection.contains(container)) {
                carouselSection.appendChild(container);
            }

            // Start auto-rotation
            startCarouselRotation();
        }
    } catch (e) {
        console.warn('Could not load carousel from CMS:', e);
    }
}

/**
 * Start carousel auto-rotation
 */
function startCarouselRotation() {
    const track = document.querySelector('.carousel-track');
    if (!track) return;

    let currentIndex = 0;
    const items = track.querySelectorAll('.carousel-item');

    setInterval(() => {
        items.forEach(item => item.style.display = 'none');
        currentIndex = (currentIndex + 1) % items.length;
        items[currentIndex].style.display = 'flex';
    }, 5000);
}

/**
 * Load content sections from CMS
 */
async function loadContentSections() {
    try {
        const response = await fetch(`${API_BASE}/api/cms/content`);
        const data = await response.json();

        if (data.success && data.content) {
            // Update various sections with CMS content
            data.content.forEach(block => {
                updateSectionContent(block.section_name, block);
            });
        }
    } catch (e) {
        console.warn('Could not load content sections from CMS:', e);
    }
}

/**
 * Update section content based on CMS data
 */
function updateSectionContent(sectionName, content) {
    const section = document.querySelector(`[data-section="${sectionName}"]`);
    if (!section) return;

    if (content.title) {
        const titleEl = section.querySelector('h2, h3, .section-title');
        if (titleEl) titleEl.textContent = content.title;
    }

    if (content.description) {
        const descEl = section.querySelector('p, .description');
        if (descEl) descEl.textContent = content.description;
    }

    if (content.button_text && content.button_link) {
        let btn = section.querySelector('button[data-cms-btn]');
        if (!btn) {
            btn = document.createElement('button');
            btn.setAttribute('data-cms-btn', 'true');
            btn.className = 'btn btn-primary';
            section.appendChild(btn);
        }
        btn.textContent = content.button_text;
        btn.onclick = () => window.location.href = content.button_link;
    }
}

/**
 * Open video in modal
 */
function openVideoModal(videoUrl) {
    const modal = document.getElementById('videoModal') || createVideoModal();
    const iframe = modal.querySelector('iframe');

    // Handle YouTube URLs
    if (videoUrl.includes('youtube.com') || videoUrl.includes('youtu.be')) {
        const youtubeId = extractYoutubeId(videoUrl);
        iframe.src = `https://www.youtube.com/embed/${youtubeId}`;
    } else {
        // Direct video file
        const video = modal.querySelector('video');
        if (video) {
            video.src = videoUrl;
            video.style.display = 'block';
            iframe.style.display = 'none';
        }
    }

    modal.classList.add('active');
}

/**
 * Create video modal if it doesn't exist
 */
function createVideoModal() {
    const modal = document.createElement('div');
    modal.id = 'videoModal';
    modal.className = 'video-modal';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="closeVideoModal()"></div>
        <div class="modal-content">
            <button class="modal-close" onclick="closeVideoModal()">&times;</button>
            <video width="100%" height="500" controls style="border-radius: 12px; display: none;"></video>
            <iframe
                width="100%"
                height="500"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
                style="border-radius: 12px;">
            </iframe>
        </div>
    `;

    Object.assign(modal.style, {
        display: 'none',
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 1000,
        alignItems: 'center',
        justifyContent: 'center',
    });

    modal.classList.add('active', {
        display: 'flex'
    });

    document.body.appendChild(modal);
    return modal;
}

/**
 * Close video modal
 */
function closeVideoModal() {
    const modal = document.getElementById('videoModal');
    if (modal) {
        modal.classList.remove('active');
        const video = modal.querySelector('video');
        if (video) {
            video.pause();
            video.src = '';
        }
    }
}

/**
 * Extract YouTube ID from various URL formats
 */
function extractYoutubeId(url) {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
}

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeVideoModal();
    }
});
