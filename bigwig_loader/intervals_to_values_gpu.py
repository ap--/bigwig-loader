import cupy as cp

_zero = cp.asarray(0.0, dtype=cp.float32).item()

_cuda_kernel = """
extern "C" __global__
void intervals_to_values(
        const int* query_starts,
        const int* query_ends,
        const int* found_starts,
        const int* found_ends,
        const int* track_starts,
        const int* track_ends,
        const float* track_values,
        const int batch_size,
        const int sequence_length,
        const int max_number_intervals,
        const int max_interval_length,
        float* out
) {

    //printf("batch_size %d", batch_size);
    //printf("sequence_length %d", sequence_length);
    //printf("max_number_intervals %d", max_number_intervals);
    //printf("max_interval_length %d", max_interval_length);

    int thread = blockIdx.x * blockDim.x + threadIdx.x;

    int i = thread % batch_size;
    int j = (thread / batch_size)%max_number_intervals;
    int k = thread / (batch_size*max_number_intervals);

    if (i <  batch_size){

        int found_start_index = found_starts[i];
        int found_end_index = found_ends[i];
        int query_start = query_starts[i];
        int query_end = query_ends[i];

        int cursor = found_start_index + j;

        if (cursor < found_end_index){
            int interval_start = track_starts[cursor];
            int interval_end = track_ends[cursor];
            int start_index = max(interval_start - query_start, 0);
            int end_index = (i * sequence_length) + min(interval_end, query_end) - query_start;
            int position = (i * sequence_length) + start_index + k;

            if (position < end_index){
                out[position] = track_values[cursor];
            }
        }
    }
}
"""

cuda_kernel = cp.RawKernel(_cuda_kernel, "intervals_to_values")
cuda_kernel.compile()


def intervals_to_values(
    track_starts: cp.ndarray,
    track_ends: cp.ndarray,
    track_values: cp.ndarray,
    query_starts: cp.ndarray,
    query_ends: cp.ndarray,
    out: cp.ndarray,
) -> cp.ndarray:
    out *= _zero
    found_starts = cp.searchsorted(track_ends, query_starts, side="right").astype(
        dtype=cp.int32
    )
    found_ends = cp.searchsorted(track_starts, query_ends, side="left").astype(
        dtype=cp.int32
    )

    sequence_length = (query_ends[0] - query_starts[0]).item()

    max_number_intervals = min(
        sequence_length, (found_ends - found_starts).max().item()
    )
    max_interval_length = min(sequence_length, (track_ends - track_starts).max().item())
    batch_size = query_starts.shape[0]
    n_threads_needed = batch_size * max_interval_length * max_number_intervals
    grid_size, block_size = get_grid_and_block_size(n_threads_needed)

    cuda_kernel(
        (grid_size,),
        (block_size,),
        (
            query_starts,
            query_ends,
            found_starts,
            found_ends,
            track_starts,
            track_ends,
            track_values,
            batch_size,
            sequence_length,
            max_number_intervals,
            max_interval_length,
            out,
        ),
    )
    return out


def get_grid_and_block_size(n_threads: int) -> tuple[int, int]:
    n_blocks_needed = cp.ceil(n_threads / 512).astype(dtype=cp.int32).item()
    if n_blocks_needed == 1:
        threads_per_block = n_threads
    else:
        threads_per_block = 512
    return n_blocks_needed, threads_per_block


def kernel_in_python(
    grid_size: int,
    block_size: int,
    args: tuple[
        cp.ndarray,
        cp.ndarray,
        cp.ndarray,
        cp.ndarray,
        cp.ndarray,
        cp.ndarray,
        cp.ndarray,
        int,
        int,
        int,
        int,
        cp.ndarray,
    ],
) -> list[float]:
    """Equivalent in python to cuda_kernel. Just for debugging."""

    (
        query_starts,
        query_ends,
        found_starts,
        found_ends,
        track_starts,
        track_ends,
        track_values,
        batch_size,
        sequence_length,
        max_number_intervals,
        max_interval_length,
        _,
    ) = args

    query_starts = query_starts.get().tolist()
    query_ends = query_ends.get().tolist()

    found_starts = found_starts.get().tolist()
    found_ends = found_ends.get().tolist()
    track_starts = track_starts.get().tolist()
    track_ends = track_ends.get().tolist()
    track_values = track_values.get().tolist()

    n_threads = grid_size * block_size

    out = [0.0] * 4 * batch_size

    for thread in range(n_threads):
        i = thread % batch_size
        j = (thread // batch_size) % max_number_intervals
        k = thread // (batch_size * max_number_intervals)
        print("---")
        print(i, j, k)

        if i < batch_size:
            found_start_index = found_starts[i]
            found_end_index = found_ends[i]
            query_start = query_starts[i]
            query_end = query_ends[i]

            cursor = found_start_index + j
            print("cursor", cursor)

            if cursor < found_end_index:
                interval_start = track_starts[cursor]
                interval_end = track_ends[cursor]
                start_index = max(interval_start - query_start, 0)
                end_index = (
                    (i * sequence_length) + min(interval_end, query_end) - query_start
                )
                position = (i * sequence_length) + start_index + k
                # position = start_index + k
                print("position", position)

                if position < end_index:
                    out[position] = track_values[cursor]
        print(out)

    print(out)
    return out
