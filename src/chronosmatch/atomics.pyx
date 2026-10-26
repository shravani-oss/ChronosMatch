# cython: language_level=3
"""Acquire/release access to 64-bit integers inside shared memory, plus memory fences.

Why this exists: on ARM CPUs (Apple Silicon), another core may see our stores in a different
order than we made them. Without these, a ring-buffer reader could see the new write index
*before* the order bytes it points to, and read the slot's previous contents. This was measured
on 26 Oct: about 1 stale read per million orders (docs/notes/04-ring-buffer.md).

- store (release): every memory write made *before* it becomes visible to other cores no later
  than this store. Used to publish an index after writing data.
- load (acquire): no memory read made *after* it can return data older than this load.
  Used to read an index before reading the data it covers.
Plain Python cannot express this ordering, so these call the C compiler's atomic built-ins.
"""

from libc.stdint cimport uint64_t

cdef extern from *:
    """
    #include <stdint.h>
    static inline uint64_t cm_load_acquire(const uint64_t *p) {
        return __atomic_load_n(p, __ATOMIC_ACQUIRE);
    }
    static inline void cm_store_release(uint64_t *p, uint64_t v) {
        __atomic_store_n(p, v, __ATOMIC_RELEASE);
    }
    static inline void cm_fence_acquire(void) { __atomic_thread_fence(__ATOMIC_ACQUIRE); }
    static inline void cm_fence_release(void) { __atomic_thread_fence(__ATOMIC_RELEASE); }
    """
    uint64_t cm_load_acquire(const uint64_t *p) nogil
    void cm_store_release(uint64_t *p, uint64_t v) nogil
    void cm_fence_acquire() nogil
    void cm_fence_release() nogil


cdef class AtomicU64:
    """An aligned unsigned 64-bit integer at `offset` inside a writable buffer (e.g. an mmap).

    Holds a view of the buffer while alive; call `release()` before closing the mmap.
    """

    cdef uint64_t* ptr
    cdef object _view

    def __cinit__(self, buffer, Py_ssize_t offset):
        cdef unsigned char[::1] view = buffer
        if offset < 0 or offset + 8 > view.shape[0]:
            raise ValueError(f"offset {offset} outside buffer of {view.shape[0]} bytes")
        if offset % 8:
            raise ValueError(f"offset {offset} is not 8-byte aligned")
        self.ptr = <uint64_t*> &view[offset]
        if (<size_t> self.ptr) % 8:
            raise ValueError("buffer address is not 8-byte aligned")
        self._view = view

    def load(self):
        """Acquire load."""
        if self.ptr == NULL:
            raise ValueError("released")
        return cm_load_acquire(self.ptr)

    def store(self, uint64_t value):
        """Release store."""
        if self.ptr == NULL:
            raise ValueError("released")
        cm_store_release(self.ptr, value)

    def release(self):
        self.ptr = NULL
        self._view = None


def fence_acquire():
    """Later reads cannot move before this point."""
    cm_fence_acquire()


def fence_release():
    """Earlier writes cannot move after this point."""
    cm_fence_release()
