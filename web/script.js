document.addEventListener('DOMContentLoaded', () => {
    const gridView = document.getElementById('grid-view');
    const readerView = document.getElementById('reader-view');
    const readerImage = document.getElementById('reader-image');
    const readerVideo = document.getElementById('reader-video');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const closeReaderBtn = document.getElementById('close-reader');
    const prevArea = document.getElementById('prev-area');
    const nextArea = document.getElementById('next-area');
    const backBtn = document.getElementById('back-btn');
    const pageSlider = document.getElementById('page-slider');
    const layoutBtn = document.getElementById('layout-btn');
    const stripView = document.getElementById('strip-view');
    const chapterTitle = document.getElementById('chapter-title');
    const readerHeader = document.getElementById('reader-header');
    const prevChapterBtn = document.getElementById('prev-chapter-btn');
    const nextChapterBtn = document.getElementById('next-chapter-btn');

    let currentPath = '';
    let currentManga = null;
    let currentSeriesData = null;
    let currentPage = 0;
    let imageList = [];
    let chapterList = [];
    let currentChapterIndex = -1;
    let layoutMode = 'single';
    let storedVolume = 1.0; // Default volume
    let storedMuted = false;

    const VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.webm', '.mov'];

    function isVideo(filename) {
        return VIDEO_EXTENSIONS.some(ext => filename.toLowerCase().endsWith(ext));
    }

    const readerImageContainer = document.getElementById('reader-image-container');

    function toggleControls(event) {
        if (layoutMode === 'strip') {
            document.getElementById('reader-controls').classList.toggle('visible');
            closeReaderBtn.classList.toggle('visible');
            readerHeader.classList.toggle('visible');
            return;
        }

        const rect = readerImageContainer.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const middleStart = rect.width * 0.2;
        const middleEnd = rect.width * 0.8;

        if (x >= middleStart && x <= middleEnd) {
            document.getElementById('reader-controls').classList.toggle('visible');
            closeReaderBtn.classList.toggle('visible');
            readerHeader.classList.toggle('visible');
        }
    }

    // Nav Button Logic
    prevChapterBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (currentChapterIndex > 0) {
            openReader(currentSeriesData, chapterList[currentChapterIndex - 1]);
        }
    });

    nextChapterBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (currentChapterIndex < chapterList.length - 1) {
            openReader(currentSeriesData, chapterList[currentChapterIndex + 1]);
        }
    });

    readerImageContainer.addEventListener('click', toggleControls);
    stripView.addEventListener('click', toggleControls);

    // Volume Persistence
    readerVideo.addEventListener('volumechange', () => {
        storedVolume = readerVideo.volume;
        storedMuted = readerVideo.muted;
    });

    function toggleLayout() {
        layoutMode = layoutMode === 'single' ? 'strip' : 'single';
        if (layoutMode === 'strip') {
            readerView.classList.add('strip-mode');
            renderStripView();
            document.getElementById('reader-image-container').style.display = 'none';
            stripView.style.display = 'block';
        } else {
            readerView.classList.remove('strip-mode');
            const images = stripView.getElementsByTagName('img');
            let topVisibleImage = 0;
            for (let i = 0; i < images.length; i++) {
                const rect = images[i].getBoundingClientRect();
                if (rect.top >= 0) {
                    topVisibleImage = i;
                    break;
                }
            }
            currentPage = topVisibleImage;
            displayPage();

            stripView.style.display = 'none';
            document.getElementById('reader-image-container').style.display = 'flex';
        }
    }

    layoutBtn.addEventListener('click', toggleLayout);

    function renderStripView() {
        stripView.innerHTML = ''; // Clear the strip view
        stripView.scrollTop = 0; // Reset scroll position

        const observer = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.onload = () => {
                        img.style.minHeight = 'auto'; // Reset min-height after load
                        img.classList.add('loaded');
                    };
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: "200% 0px" // Pre-load images 2 screens away
        });

        imageList.forEach(imagePath => {
            if (isVideo(imagePath)) {
                // Skip videos in strip view as per requirement "no strip layout mode"
                // Or render a placeholder
                const placeholder = document.createElement('div');
                placeholder.classList.add('strip-placeholder');
                placeholder.style.height = '200px';
                placeholder.style.display = 'flex';
                placeholder.style.alignItems = 'center';
                placeholder.style.justifyContent = 'center';
                placeholder.style.color = '#fff';
                placeholder.style.backgroundColor = '#333';
                placeholder.innerText = 'Video File (View in Single Mode)';
                stripView.appendChild(placeholder);
                return;
            }
            const img = document.createElement('img');
            img.dataset.src = `/images/${encodeURIComponent(imagePath)}`;
            // Add min-height to prevent layout jumping and ensure observer catches them
            img.style.minHeight = '600px';
            img.style.backgroundColor = '#222'; // Visual placeholder
            img.classList.add('lazy-thumb'); // Use existing fade-in class
            stripView.appendChild(img);
            observer.observe(img);
        });
    }

    const chapterListView = document.getElementById('chapter-list-view');

    function loadGrid(path) {
        currentPath = path;
        gridView.innerHTML = ''; // Clear the grid

        fetch('/api/folders')
            .then(response => response.json())
            .then(items => {
                items.forEach(item => {
                    const gridItem = document.createElement('div');
                    gridItem.classList.add('grid-item');
                    gridItem.innerHTML = `
                        <img src="/images/${encodeURIComponent(item.cover_image)}?width=150&quality=50" alt="${item.name}">
                        <p>${item.name}</p>
                    `;
                    gridItem.addEventListener('click', () => {
                        showChapterList(item);
                    });
                    gridView.appendChild(gridItem);
                });
            });
    }

    backBtn.addEventListener('click', () => {
        if (chapterListView.style.display === 'block') {
            chapterListView.style.display = 'none';
            gridView.style.display = 'grid';
            loadGrid(currentPath);
            return;
        }

        if (currentPath) {
            const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/'));
            loadGrid(parentPath);
        }
    });

    function showChapterList(series) {
        gridView.style.display = 'none';
        chapterListView.style.display = 'block';
        chapterListView.innerHTML = ''; // Clear the view

        fetch(`/api/series/${encodeURIComponent(series.name)}`)
            .then(response => response.json())
            .then(seriesData => {
                if (seriesData.chapters && seriesData.chapters.length > 0) {
                    const header = document.createElement('div');
                    header.id = 'series-header';
                    header.innerHTML = `
                        <img src="/images/${seriesData.cover_image}" alt="${seriesData.name}">
                        <h1>${seriesData.name}</h1>
                    `;
                    chapterListView.appendChild(header);

                    const chapterList = document.createElement('ul');
                    chapterList.id = 'chapter-list';

                    // Lazy loading observer for chapters
                    const chapterObserver = new IntersectionObserver((entries, observer) => {
                        entries.forEach(entry => {
                            if (entry.isIntersecting) {
                                const img = entry.target;
                                img.src = img.dataset.src;
                                img.classList.add('loaded'); // Optional: for fade-in effects
                                observer.unobserve(img);
                            }
                        });
                    });

                    seriesData.chapters.forEach(chapter => {
                        const chapterItem = document.createElement('li');
                        chapterItem.classList.add('chapter-item');

                        // Use data-src for lazy loading
                        // Added loading='lazy' as standard attribute fallback, though JS observer is primary here
                        chapterItem.innerHTML = `<img data-src="/images/${encodeURIComponent(chapter.thumbnail)}?width=150&quality=50" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" class="lazy-thumb" alt="${chapter.name}"><span>${chapter.name}</span>`;

                        chapterItem.addEventListener('click', () => {
                            // Disconnect observer to stop pending loads when switching view
                            chapterObserver.disconnect();
                            openReader(seriesData, chapter);
                        });
                        chapterList.appendChild(chapterItem);

                        // Start observing the image
                        const img = chapterItem.querySelector('img');
                        chapterObserver.observe(img);
                    });
                    chapterListView.appendChild(chapterList);
                } else {
                    openReader(seriesData, null);
                }
            });
    }

    // Initial load
    loadGrid('');



    function openReader(seriesData, chapter, startPage = 'first') {
        currentManga = seriesData.path;
        currentSeriesData = seriesData;

        gridView.style.display = 'none';
        chapterListView.style.display = 'none';
        document.getElementById('controls').classList.add('hidden');
        readerView.classList.add('visible');

        // Apply View Logic Helper
        const applyView = () => {
            if (layoutMode === 'strip') {
                readerView.classList.add('strip-mode');
                document.getElementById('reader-image-container').style.display = 'none';
                stripView.style.display = 'block';
                renderStripView();
            } else {
                readerView.classList.remove('strip-mode');
                document.getElementById('reader-image-container').style.display = 'flex';
                stripView.style.display = 'none';
                displayPage();
            }
        };

        if (chapter) {
            chapterTitle.innerText = chapter.name;
            chapterList = seriesData.chapters;
            currentChapterIndex = chapterList.findIndex(c => c.path === chapter.path);
            imageList = chapter.images;
            pageSlider.max = imageList.length - 1;
            currentPage = startPage === 'last' ? imageList.length - 1 : 0;
            applyView();
        } else { // Series with no chapters
            chapterTitle.innerText = seriesData.name;
            chapterList = [];
            currentChapterIndex = 0;
            fetch(`/api/images?path=${encodeURIComponent(seriesData.path)}`)
                .then(response => response.json())
                .then(images => {
                    imageList = images;
                    pageSlider.max = imageList.length - 1;
                    currentPage = 0;
                    applyView();
                });
        }
    }

    function displayPage() {
        if (currentPage >= 0 && currentPage < imageList.length) {
            const currentFile = imageList[currentPage];
            if (isVideo(currentFile)) {
                readerImage.style.display = 'none';
                readerVideo.style.display = 'block';
                readerVideo.src = `/images/${encodeURIComponent(currentFile)}`;

                // Restore volume settings
                readerVideo.volume = storedVolume;
                readerVideo.muted = storedMuted;

                layoutBtn.style.display = 'none'; // Disable strip mode for video
            } else {
                readerVideo.pause();
                readerVideo.style.display = 'none';
                readerImage.style.display = 'block';
                readerImage.src = `/images/${encodeURIComponent(currentFile)}`;
                layoutBtn.style.display = 'inline-block';
            }
            pageSlider.value = currentPage;
        }
    }

    function showNextPage() {
        if (currentPage < imageList.length - 1) {
            currentPage++;
            displayPage();
        } else {
            if (currentChapterIndex < chapterList.length - 1) {
                openReader(currentSeriesData, chapterList[currentChapterIndex + 1]);
            }
        }
    }

    function showPrevPage() {
        if (currentPage > 0) {
            currentPage--;
            displayPage();
        } else {
            if (currentChapterIndex > 0) {
                openReader(currentSeriesData, chapterList[currentChapterIndex - 1], 'last');
            }
        }
    }

    pageSlider.addEventListener('input', (e) => {
        currentPage = parseInt(e.target.value, 10);
        displayPage();
    });

    nextArea.addEventListener('click', showNextPage);
    prevArea.addEventListener('click', showPrevPage);

    closeReaderBtn.addEventListener('click', () => {
        readerView.classList.remove('visible');

        if (currentSeriesData && currentSeriesData.chapters && currentSeriesData.chapters.length > 0) {
            chapterListView.style.display = 'block';
        } else {
            gridView.style.display = 'grid';
        }

        readerVideo.pause();
        readerVideo.src = "";
        layoutBtn.style.display = 'inline-block'; // Reset layout button visibility

        document.getElementById('controls').classList.remove('hidden');

        // Reset reader-specific state
        currentManga = null;
        imageList = [];
        currentPage = 0;
    });

    document.addEventListener('keydown', (e) => {
        if (readerView.classList.contains('visible')) {
            if (e.key === 'ArrowRight') {
                showNextPage();
            } else if (e.key === 'ArrowLeft') {
                showPrevPage();
            }
        }
    });
});