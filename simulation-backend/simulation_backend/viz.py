import numpy as np
import matplotlib.pyplot as plt

# Load file
data = np.load("simulation-backend/simulation_backend/headless_backend/output/dg_sim_results.npz")

# List all keys
print(data.files)

# arr = data["IR"]
arr = data["IR_Uncorrected"]
print(arr.shape, arr.dtype)

# ts = 
plt.plot(arr[0, :], '*')
plt.title("1D Array")
plt.show()

# plt.imshow(arr, cmap="viridis", aspect="auto")
# plt.colorbar()
# plt.title("2D Array")
# plt.show()

# # Show one slice
# plt.imshow(arr[0], cmap="gray")
# plt.title("First slice of 3D array")
# plt.show()
