import numpy as np

def add_gaussian_noise(image):
    row, col, ch = image.shape
    mean = 0
    sigma = 4.0
    gauss = np.random.normal(mean, sigma, (row, col, ch))
    gauss = gauss.reshape(row, col, ch)
    noisy = image + gauss
    return np.clip(noisy, 0, 255).astype(np.uint8)