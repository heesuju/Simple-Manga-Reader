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

    let currentPath = '';
    let currentManga = null;
    let currentPage = 0;
    let imageList = [];
    let chapterList = [];
    let currentChapterIndex = -1;

    function loadGrid(path) {
        currentPath = path;
        gridView.innerHTML = ''; // Clear the grid

        fetch(`/api/folders?path=${encodeURIComponent(path)}`)
            .then(response => response.json())
            .then(items => {
                items.forEach(item => {
                    const gridItem = document.createElement('div');
                    gridItem.classList.add('grid-item');
                    gridItem.innerHTML = `
                        <img src="/images/${item.thumbnail}" alt="${item.name}">
                        <p>${item.name}</p>
                    `;
                    gridItem.addEventListener('click', () => {
                        if (item.type === 'folder') {
                            loadGrid(item.path);
                        } else {
                            openReader(item.path);
                        }
                    });
                    gridView.appendChild(gridItem);
                });
            });
    }

    // Initial load
    loadGrid('');

    backBtn.addEventListener('click', () => {
        const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/'));
        loadGrid(parentPath);
    });

    function openReader(mangaDir, startAt = 'first') {
        currentManga = mangaDir;
        
        gridView.classList.add('hidden');
        document.getElementById('controls').classList.add('hidden');
        readerView.classList.add('visible');

        fetch(`/api/series?path=${encodeURIComponent(mangaDir)}`)
            .then(response => response.json())
            .then(chapters => {
                chapterList = chapters;
                currentChapterIndex = chapterList.indexOf(mangaDir);
            });

        fetch(`/api/images?path=${encodeURIComponent(mangaDir)}`)
            .then(response => response.json())
            .then(images => {
                imageList = images;
                pageSlider.max = imageList.length - 1;
                if (startAt === 'last') {
                    currentPage = imageList.length - 1;
                } else {
                    currentPage = 0;
                }
                displayPage();
            });
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

    nextPageBtn.addEventListener('click', showNextPage);
    prevPageBtn.addEventListener('click', showPrevPage);
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