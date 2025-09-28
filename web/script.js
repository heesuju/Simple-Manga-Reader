document.addEventListener('DOMContentLoaded', () => {
    const gridView = document.getElementById('grid-view');
    const readerView = document.getElementById('reader-view');
    const readerImage = document.getElementById('reader-image');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const closeReaderBtn = document.getElementById('close-reader');
    const prevArea = document.getElementById('prev-area');
    const nextArea = document.getElementById('next-area');
    const backBtn = document.getElementById('back-btn');
    const pageSlider = document.getElementById('page-slider');
    const layoutBtn = document.getElementById('layout-btn');
    const stripView = document.getElementById('strip-view');

    let currentPath = '';
    let currentManga = null;
    let currentPage = 0;
    let imageList = [];
    let chapterList = [];
    let currentChapterIndex = -1;
    let layoutMode = 'single';

    const readerImageContainer = document.getElementById('reader-image-container');

    function toggleControls(event) {
        const rect = readerImageContainer.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const middleStart = rect.width * 0.2;
        const middleEnd = rect.width * 0.8;

        if (x >= middleStart && x <= middleEnd) {
            document.getElementById('reader-controls').classList.toggle('visible');
            closeReaderBtn.classList.toggle('visible');
        }
    }

    readerImageContainer.addEventListener('click', toggleControls);

    function toggleLayout() {
        layoutMode = layoutMode === 'single' ? 'strip' : 'single';
        if (layoutMode === 'strip') {
            renderStripView();
            document.getElementById('reader-image-container').style.display = 'none';
            stripView.style.display = 'block';
        } else {
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

        const observer = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    observer.unobserve(img);
                }
            });
        });

        imageList.forEach(imagePath => {
            const img = document.createElement('img');
            img.dataset.src = `/images/${imagePath}`;
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
                        <img src="/images/${item.cover_image}?width=150&quality=50" alt="${item.name}">
                        <p>${item.name}</p>
                    `;
                    gridItem.addEventListener('click', () => {
                        showChapterList(item);
                    });
                    gridView.appendChild(gridItem);
                });
            });
    }

    const backToGridBtn = document.getElementById('back-to-grid-btn');

    backToGridBtn.addEventListener('click', () => {
        gridView.style.display = 'grid';
        chapterListView.style.display = 'none';
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
                    seriesData.chapters.forEach(chapter => {
                        const chapterItem = document.createElement('li');
                        chapterItem.classList.add('chapter-item');
                        chapterItem.innerHTML = `<img src="/images/${chapter.thumbnail}?width=150&quality=50" alt="${chapter.name}"><span>${chapter.name}</span>`;
                        chapterItem.addEventListener('click', () => {
                            openReader(seriesData, chapter);
                        });
                        chapterList.appendChild(chapterItem);
                    });
                    chapterListView.appendChild(chapterList);
                } else {
                    openReader(seriesData, null);
                }
            });
    }

    // Initial load
    loadGrid('');

    backBtn.addEventListener('click', () => {
        const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/'));
        loadGrid(parentPath);
    });

    function openReader(seriesData, chapter) {
        currentManga = seriesData.path;
        
        gridView.style.display = 'none';
        chapterListView.style.display = 'none';
        document.getElementById('controls').classList.add('hidden');
        readerView.classList.add('visible');

        layoutMode = 'single';
        stripView.style.display = 'none';
        document.getElementById('reader-image-container').style.display = 'flex';

        if (chapter) {
            chapterList = seriesData.chapters;
            currentChapterIndex = chapterList.indexOf(chapter);
            imageList = chapter.images;
            pageSlider.max = imageList.length - 1;
            currentPage = 0;
            displayPage();
        } else { // Series with no chapters
            chapterList = [];
            currentChapterIndex = 0;
            fetch(`/api/images?path=${encodeURIComponent(seriesData.path)}`)
                .then(response => response.json())
                .then(images => {
                    imageList = images;
                    pageSlider.max = imageList.length - 1;
                    currentPage = 0;
                    displayPage();
                });
        }
    }

    function displayPage() {
        if (currentPage >= 0 && currentPage < imageList.length) {
            readerImage.src = `/images/${imageList[currentPage]}`;
            pageSlider.value = currentPage;
        }
    }

    function showNextPage() {
        if (currentPage < imageList.length - 1) {
            currentPage++;
            displayPage();
        } else {
            if (currentChapterIndex < chapterList.length - 1) {
                openReader(chapterList[currentChapterIndex + 1]);
            }
        }
    }

    function showPrevPage() {
        if (currentPage > 0) {
            currentPage--;
            displayPage();
        } else {
            if (currentChapterIndex > 0) {
                openReader(chapterList[currentChapterIndex - 1], 'last');
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
        currentManga = null;
        gridView.classList.remove('hidden');
        document.getElementById('controls').classList.remove('hidden');
        readerView.classList.remove('visible');
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